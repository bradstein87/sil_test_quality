"""!
@brief Tests for file selection and source structure checks.
"""

import pytest

from sil_test_quality.source import ProjectSource


class TestProjectSource:
    """!
    @brief Check exclusions, file length and test organization.
    """

    @pytest.mark.parametrize(
        "filename, declaration",
        [
            ("test_example.py", "def test_example():\n    pass\n"),
            ("example_test.py", "async def test_example():\n    pass\n"),
        ],
    )
    def test_function_tests_require_a_class(
        self, tmp_path, filename, declaration
    ):
        """!
        @brief Require repo test functions to belong to a class.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param filename Test-module filename convention to exercise.
        @param declaration Top-level test function written into the sample
        module.
        """

        tests = tmp_path / "tests/unit"
        tests.mkdir(parents=True)
        (tests / filename).write_text(declaration)
        problems, _ = ProjectSource(tmp_path).inspect()
        assert problems == [
            f"{(tests / filename).relative_to(tmp_path)}:1: "
            "put test_example in a Test class"
        ]

    def test_methods_fixtures_helpers_and_embedded_tests_are_allowed(
        self, tmp_path
    ):
        """!
        @brief Allow test methods, fixtures and support functions.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """

        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_example.py").write_text(
            "import pytest\nfrom pytest import fixture\n\n"
            "@pytest.fixture\ndef test_data():\n    return 1\n\n"
            "@fixture(scope='module')\ndef test_connection():\n    return 2\n\n"
            "def helper():\n    return 'def test_example(): pass'\n\n"
            "class TestExample:\n"
            "    def test_answer(self, test_data):\n"
            "        assert test_data == 1\n\n"
            "    async def test_async(self):\n        pass\n"
        )
        assert ProjectSource(tmp_path).inspect() == ([], [])

    @pytest.mark.parametrize(
        "filename", ["tests/support.py", "src/test_example.py"]
    )
    def test_rule_applies_only_to_repository_test_modules(
        self, tmp_path, filename
    ):
        """!
        @brief Limit the test-class rule to repo test modules.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param filename Source/support path where a top-level function should be
        allowed.
        """

        path = tmp_path / filename
        path.parent.mkdir(parents=True)
        path.write_text("def test_example():\n    pass\n")
        assert ProjectSource(tmp_path).inspect() == ([], [])

    def test_file_limit_includes_comments_and_allows_exactly_500_lines(
        self, tmp_path
    ):
        """!
        @brief Allow 500 physical lines and reject files above that limit.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """

        (tmp_path / "allowed.py").write_text("# explanation\n" * 500)
        (tmp_path / "too_long.py").write_text("# explanation\n" * 501)
        assert ProjectSource(tmp_path).sizes() == {
            "allowed.py": 500,
            "too_long.py": 501,
        }

    def test_generated_files_and_binary_assets_are_excluded(self, tmp_path):
        """!
        @brief Skip generated content and binary files in line checks.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """

        for name in (".venv", "venv", "artifacts", "project.egg-info"):
            directory = tmp_path / name
            directory.mkdir()
            if name in (".venv", "venv"):
                (directory / "pyvenv.cfg").touch()
            (directory / "generated.txt").write_text("line\n" * 501)
        (tmp_path / "image.bin").write_bytes(b"\xff\x00\n" * 501)
        (tmp_path / "nulls.bin").write_bytes(b"\x00\n" * 501)
        assert ProjectSource(tmp_path).sizes() == {}

    @pytest.mark.parametrize(
        "entry",
        [
            "src/legacy",
            "legacy/*.py",
            "../old_tool.py",
            "/old_tool.py",
            "C:/old_tool.py",
        ],
    )
    def test_temporary_exclusions_require_specific_repository_files(
        self, project_with_legacy_file, entry
    ):
        """!
        @brief Reject broad or out-of-repo legacy exclusions.
        @param project_with_legacy_file Fixture repo with invalid legacy files
        and explicit exclusions.
        @param entry Invalid filename or pattern written into EXCLUDED_FILES.
        """

        root = project_with_legacy_file
        (root / "tools/exclusions.py").write_text(
            f"EXCLUDED_FILES = ({entry!r},)\n"
        )
        with pytest.raises(ValueError, match="exclusions.py"):
            ProjectSource(root)


class TestLineWidths:
    """!
    @brief Check the column limit independently of Ruff's exceptions.
    """

    @pytest.mark.parametrize("suffix", [".py", ".pyi", ".pyw"])
    def test_boundary_tabs_and_windows_newlines(self, tmp_path, suffix):
        """!
        @brief Allow 80 columns and reject 81, including expanded indentation.
        @param tmp_path Temporary repo containing the measured source file.
        @param suffix Python file extension covered by the width check.
        """
        path = tmp_path / f"sample{suffix}"
        path.write_bytes(
            ("x" * 80 + "\r\n" + "x" * 81 + "\r\n\t" + "x" * 77).encode()
        )
        findings, widths = ProjectSource(tmp_path).line_widths()
        assert widths == {f"sample{suffix}": 81}
        assert findings == [
            f"sample{suffix}:2: 81 columns (limit is 80)",
            f"sample{suffix}:3: 81 columns (limit is 80)",
        ]

    @pytest.mark.parametrize(
        "line",
        [
            "identifier_" + "x" * 70,
            "#" + "x" * 80,
            '"""' + "x" * 75 + '"""',
            "# https://example.com/".ljust(81, "x"),
            "VALUE = 1".ljust(70) + "  # noqa: E501",
        ],
        ids=["identifier", "comment", "docstring", "url", "noqa"],
    )
    def test_ruff_exceptions_do_not_bypass_width(self, tmp_path, line):
        """!
        @brief Reject overlong lines even when Ruff would allow them.
        @param tmp_path Temporary repo containing the measured source file.
        @param line Code or documentation that exceeds the shared limit.
        """
        (tmp_path / "sample.py").write_text(line, encoding="utf-8")
        assert ProjectSource(tmp_path).line_widths()[0] == [
            f"sample.py:1: {len(line)} columns (limit is 80)"
        ]

    def test_findings_are_widest_first(self, tmp_path):
        """!
        @brief Put the longest lines first, regardless of filename or location.
        @param tmp_path Temporary repo with several overlong source lines.
        """
        (tmp_path / "a.py").write_text("x" * 81 + "\n" + "x" * 110)
        (tmp_path / "z.py").write_text("x" * 90)
        assert ProjectSource(tmp_path).line_widths()[0] == [
            "a.py:2: 110 columns (limit is 80)",
            "z.py:1: 90 columns (limit is 80)",
            "a.py:1: 81 columns (limit is 80)",
        ]

    def test_scope_respects_exclusions(self, project_with_legacy_file):
        """!
        @brief Skip generated, excluded and non-Python files.
        @param project_with_legacy_file Temporary repo with legacy exclusions.
        """
        root = project_with_legacy_file
        for name in ("artifacts", "custom-python"):
            directory = root / name
            directory.mkdir()
            if name == "custom-python":
                (directory / "pyvenv.cfg").touch()
            (directory / "generated.py").write_text("x" * 81)
        (root / "src/legacy/old_tool.py").write_text("x" * 81)
        (root / "README.md").write_text("x" * 81)
        assert ProjectSource(root).line_widths()[0] == []
        (root / "tools/helper.py").write_text("x" * 81)
        assert ProjectSource(root).line_widths()[0] == [
            "tools/helper.py:1: 81 columns (limit is 80)"
        ]

    @pytest.mark.parametrize("content", [b"\xff", b"# coding: unknown-codec\n"])
    def test_invalid_encoding_fails_the_check(self, tmp_path, content):
        """!
        @brief Report files that cannot be read instead of accepting them.
        @param tmp_path Temporary repo containing the unreadable source file.
        @param content Invalid encoded bytes or an unsupported encoding header.
        """
        (tmp_path / "sample.py").write_bytes(content)
        findings, widths = ProjectSource(tmp_path).line_widths()
        assert widths == {}
        assert len(findings) == 1
        assert findings[0].startswith("sample.py:1: cannot measure lines:")

    def test_declared_encoding_counts_characters(self, tmp_path):
        """!
        @brief Measure decoded characters using the file's Python encoding.
        @param tmp_path Temporary repo containing non-UTF-8 source.
        """
        (tmp_path / "sample.py").write_bytes(
            b"# coding: latin-1\n#" + b"\xe9" * 79
        )
        assert ProjectSource(tmp_path).line_widths() == ([], {"sample.py": 80})


class TestSourceStructure:
    """!
    @brief Check source violations without flagging example text.
    """

    def test_source_rules_ignore_strings_and_generated_code(self, tmp_path):
        """!
        @brief Keep strings and generated files out of source findings.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """

        (tmp_path / "valid.py").write_text('TEXT = "TODO: not a comment"\n')
        (tmp_path / "invalid.py").write_text(
            "# FIXME: unfinished work\n"
            "class Combined(First, Second):\n    pass\n"
            "def large():\n" + "    value = 1\n" * 61
        )
        (tmp_path / "syntax.py").write_text("def broken(\n")
        (tmp_path / "suppressed.py").write_text(
            "import os  # noqa: F401\n# mypy: ignore-errors\n"
        )
        generated = tmp_path / "custom-environment"
        generated.mkdir()
        (generated / "pyvenv.cfg").touch()
        (generated / "ignored.py").write_text("# TODO: generated\n")
        errors, suppressions = ProjectSource(tmp_path).inspect()
        assert len(errors) == 3
        assert any("multiple inheritance" in error for error in errors)
        assert any("unfinished work comment" in error for error in errors)
        assert any("cannot inspect" in error for error in errors)
        assert suppressions == [
            "suppressed.py:1: # noqa: F401",
            "suppressed.py:2: # mypy: ignore-errors",
        ]

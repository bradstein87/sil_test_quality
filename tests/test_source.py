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
        problems = ProjectSource(tmp_path).sizes()
        assert problems == ["too_long.py: 501 lines (limit is 500)"]

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
        assert ProjectSource(tmp_path).sizes() == []

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
        (tmp_path / "suppressed.py").write_text("import os  # noqa: F401\n")
        generated = tmp_path / "custom-environment"
        generated.mkdir()
        (generated / "pyvenv.cfg").touch()
        (generated / "ignored.py").write_text("# TODO: generated\n")
        errors, suppressions = ProjectSource(tmp_path).inspect()
        assert len(errors) == 3
        assert any("multiple inheritance" in error for error in errors)
        assert any("unfinished work comment" in error for error in errors)
        assert any("cannot inspect" in error for error in errors)
        assert suppressions == ["suppressed.py:1: # noqa: F401"]

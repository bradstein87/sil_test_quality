"""!
@brief Sample repos shared by the precommit tests.
"""

import pytest


@pytest.fixture
def checked_project(tmp_path):
    """!
    @brief Create a small repo with passing checks.
    @param tmp_path Pytest temporary directory for the sample files and
    artifacts.
    @return Repo directory for tests to check or modify for a failure scenario.
    """

    (tmp_path / "pyproject.toml").write_text(
        '[tool.sil-test-quality]\nversion = "0.1.0"\n'
        'test-label = "Harness software tests"\n'
        'coverage-omit = ["src/vv_test_verification/cases/*"]\n'
    )
    source = tmp_path / "src"
    source.mkdir()
    (source / "example.py").write_text(
        '"""! @brief Example source."""\n\nANSWER = 42\n'
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text(
        '"""! @brief Check the example."""\n\n'
        "from src.example import ANSWER\n\n\nclass TestExample:\n"
        '    """! @brief Example checks."""\n\n'
        "    def test_answer(self):\n"
        '        """! @brief Check the fixed answer."""\n'
        "        assert ANSWER == 42\n"
    )
    return tmp_path


@pytest.fixture
def project_with_legacy_file(checked_project):
    """!
    @brief Add excluded legacy files to the sample repo.
    @param checked_project Fixture repo with passing source and tests to build
    this scenario on.
    @return Repo path with invalid legacy files named in tools/exclusions.py.
    """

    root = checked_project
    (root / "tools").mkdir()
    exclusions = root / "tools/exclusions.py"
    exclusions.write_text(
        '"""! @brief Legacy source exclusions."""\n\n'
        'EXCLUDED_FILES = ("src/legacy/old_tool.py", "src/root_tool.py")\n',
        encoding="utf-8",
    )
    (root / "src/legacy").mkdir()
    (root / "src/legacy/__init__.py").touch()
    (root / "src/legacy/old_tool.py").write_text("not valid Python\n" * 501)
    (root / "src/root_tool.py").write_text("not valid Python\n" * 501)
    return root


@pytest.fixture
def unformatted_project(project_with_legacy_file):
    """!
    @brief Add repairable style errors beside excluded files.
    @param project_with_legacy_file Fixture repo with invalid legacy files and
    explicit exclusions.
    @return Repo path used to check formatting detection and repair.
    """
    root = project_with_legacy_file
    (root / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 80\n[tool.ruff.lint]\nextend-select ="
        ' ["I", "E501"]\n'
        '[tool.sil-test-quality]\nversion = "0.1.0"\n'
    )
    test_file = root / "tests/test_example.py"
    test_file.write_text(
        '"""! @brief Check parameterized answers."""\n'
        "import pytest\nfrom src.example import ANSWER\n\n"
        "class TestExample:\n"
        '    """! @brief Parameterized answer checks."""\n'
        '    @pytest.mark.parametrize("expected", [\n'
        '        pytest.param(42, id="A readable name for this answer '
        'returned by example"),\n'
        "    ])\n    def test_answer(self, expected):\n"
        '        """! @brief Check the selected answer.\n'
        "        @param expected Answer supplied by parametrization.\n"
        '        """\n'
        "        assert ANSWER == expected\n"
    )
    return root


@pytest.fixture
def partially_covered_project(checked_project):
    """!
    @brief Create high overall coverage with one uncovered path.
    @param checked_project Fixture repo with passing source and tests to build
    this scenario on.
    @return Repo path with a source file at 75% despite overall coverage above
    95%.
    """
    root = checked_project
    source = '"""! @brief Example constants."""\n\nANSWER = 42\n'
    for number in range(20):
        source += f"VALUE_{number} = {number}\n"
    (root / "src/example.py").write_text(source)
    (root / "src/choice.py").write_text(
        '"""! @brief Example conditional."""\n\n\n'
        "def choose(value):\n"
        '    """! @brief Select text from a boolean.\n'
        "    @param value Boolean condition.\n"
        "    @return Yes or no.\n"
        '    """\n'
        '    if value:\n        return "yes"\n'
        '    return "no"\n'
    )
    test = root / "tests/test_example.py"
    test.write_text(
        '"""! @brief Check conditional answers."""\n\n'
        "from src.choice import choose\nfrom src.example import ANSWER\n"
        "\n\nclass TestExample:\n"
        '    """! @brief Conditional answer checks."""\n\n'
        "    def test_answer(self):\n"
        '        """! @brief Exercise conditional behavior."""\n'
        "        assert ANSWER == 42\n"
        '        assert choose(True) == "yes"\n'
    )
    return root

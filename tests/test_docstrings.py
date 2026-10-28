"""!
@brief Tests for the Python Doxygen documentation checks.
"""

from textwrap import dedent

import pytest

from sil_test_quality.docstrings import DoxygenDocstrings
from sil_test_quality.output import CheckOutput
from sil_test_quality.source import ProjectSource


@pytest.fixture
def inspect_source(tmp_path):
    """!
    @brief Provide a checker for temporary documentation examples.
    @param tmp_path Pytest temporary directory for the sample files and
    artifacts.
    @return Helper taking Python source text and returning its documentation
    issues.
    """

    def inspect(body):
        """!
        @brief Write and check one documentation example.
        @param body Sample Python source to write into the temporary module.
        @return Documentation messages for the test to inspect. Empty for valid
        input.
        """
        path = tmp_path / "sample.py"
        path.write_text(
            '"""! @brief Documentation checker sample."""\n' + dedent(body)
        )
        return DoxygenDocstrings().check(path)

    return inspect


class TestDoxygenDocstrings:
    """!
    @brief Check docstring rules using small source examples.
    """

    @pytest.mark.parametrize(
        "docstring, message",
        [
            ("", "missing Doxygen docstring"),
            ('"""Ordinary documentation."""', 'must start with """!'),
            ('"! @brief Single-quoted documentation."', 'must start with """!'),
            ('"""! Nothing describes the purpose."""', "nonempty @brief"),
            ('"""! @brief\n    @note Something."""', "nonempty @brief"),
            ('"""! @brief First.\n    @brief Second."""', "nonempty @brief"),
            ('"""! @brief TODO: describe this."""', "unfinished"),
            ('"""! @brief FIXME: describe this."""', "unfinished"),
            ('"""! @brief Work.\n    @warning"""', "empty @warning"),
            ('"""! @brief Work.\n    @details"""', "empty @details"),
            (
                '"""! @brief Work.\n    @throws ValueError"""',
                "exception and description",
            ),
        ],
    )
    def test_missing_and_incomplete_blocks_fail(
        self, inspect_source, docstring, message
    ):
        """!
        @brief Reject missing or incomplete documentation blocks.
        @param inspect_source Fixture helper taking sample Python text and
        returning documentation issues.
        @param docstring Invalid docstring inserted into the sample function.
        @param message Diagnostic fragment expected for this example.
        """
        problems = inspect_source(f"def action():\n    {docstring}\n    pass\n")
        assert any(message in problem for problem in problems)

    def test_modules_classes_and_private_helpers_are_checked(self, tmp_path):
        """!
        @brief Require docs for modules, classes and private helpers.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        path = tmp_path / "sample.py"
        path.write_text(
            "class Example:\n    def _helper(self):\n"
            "        def nested():\n            pass\n"
        )
        problems = DoxygenDocstrings().check(path)
        assert len(problems) == 4
        assert all("missing Doxygen docstring" in item for item in problems)
        path.write_text("# Empty package file.\n")
        assert DoxygenDocstrings().check(path) == []

    def test_bound_and_variadic_arguments(self, inspect_source):
        """!
        @brief Match parameter tags to caller-supplied arguments.
        @param inspect_source Fixture helper taking sample Python text and
        returning documentation issues.
        """
        assert (
            inspect_source('''
            class Example:
                """! @brief Sample class."""
                @classmethod
                async def action(cls, first, /, *args, option=None, **kwargs):
                    """! @brief Process caller inputs.
                    @param[in] first First positional input.
                    @param *args Remaining positional inputs.
                    @param option Optional setting.
                    @param **kwargs Additional keyword inputs.
                    """
                    pass
                def idle(self) -> None:
                    """! @brief Leave the object idle."""
                    return None
                @staticmethod
                def explicit(self):
                    """! @brief Accept an ordinary argument named self.
                    @param self Caller-supplied value, not a bound instance.
                    """
                    pass
        ''')
            == []
        )

    def test_parameter_names_and_descriptions(self, inspect_source):
        """!
        @brief Reject missing or incorrect parameter descriptions.
        @param inspect_source Fixture helper taking sample Python text and
        returning documentation issues.
        """
        problems = inspect_source('''
            def action(first, second):
                """! @brief Process inputs.
                @param first A value.
                @param first Repeated description.
                @param other Nonexistent parameter.
                @param second
                """
                pass
        ''')
        assert len(problems) == 4
        assert any("duplicate @param first" in item for item in problems)
        assert any("unexpected @param other" in item for item in problems)
        assert any("missing @param second" in item for item in problems)
        assert any("name and description" in item for item in problems)

    @pytest.mark.parametrize(
        "signature, body, needs_return",
        [
            ("()", "pass", False),
            ("()", "return", False),
            ("() -> None", "return None", False),
            ("() -> None", "return cleanup()", False),
            ('() -> "None"', "pass", False),
            ("() -> int", "raise ValueError()", True),
            ("() -> NoReturn", "raise ValueError()", False),
            ("() -> typing.Never", "raise ValueError()", False),
            ("()", "return 42", True),
            ("()", "return get_value()", True),
            ("()", "yield 42", True),
            ("()", "yield from values", True),
        ],
    )
    def test_return_fields_follow_function_contract(
        self, inspect_source, signature, body, needs_return
    ):
        """!
        @brief Require return documentation when a function returns a value.
        @param inspect_source Fixture helper taking sample Python text and
        returning documentation issues.
        @param signature Sample function signature, including any return
        annotation.
        @param body Return, yield or other statement used as the function body.
        @param needs_return True when this example should require return
        documentation.
        """
        problems = inspect_source(
            f'def action{signature}:\n    """! @brief Sample."""\n    {body}\n'
        )
        assert bool(problems) is needs_return
        if needs_return:
            assert "@return" in problems[0]

    def test_nested_returns_do_not_change_outer_contract(self, inspect_source):
        """!
        @brief Keep nested returns out of the outer function's contract.
        @param inspect_source Fixture helper taking sample Python text and
        returning documentation issues.
        """
        assert (
            inspect_source('''
            def outer():
                """! @brief Define a local helper."""
                def inner():
                    """! @brief Read a fixed value.
                    @return The fixed value.
                    """
                    return 42
        ''')
            == []
        )

    def test_multiline_fields_and_code_examples(self, inspect_source):
        """!
        @brief Allow continued descriptions and tags inside code examples.
        @param inspect_source Fixture helper taking sample Python text and
        returning documentation issues.
        """
        assert (
            inspect_source('''
            def action(value):
                r"""! @brief Read a value.
                @param value
                    Value supplied by the caller.
                @returns The same value.
                @throws ValueError If a future implementation rejects it.
                @code
                @param imaginary This is an example, not a real parameter.
                @endcode
                """
                return value
        ''')
            == []
        )

    def test_duplicate_and_empty_returns_fail(self, inspect_source):
        """!
        @brief Reject empty or repeated return descriptions.
        @param inspect_source Fixture helper taking sample Python text and
        returning documentation issues.
        """
        problems = inspect_source('''
            def action():
                """! @brief Read a value.
                @return
                @returns A value.
                """
                return 42
        ''')
        assert any("empty @return" in item for item in problems)
        assert any("only one @return" in item for item in problems)

    def test_unreadable_and_invalid_source_fail(self, tmp_path):
        """!
        @brief Report source files that cannot be inspected.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        """
        path = tmp_path / "sample.py"
        assert "cannot inspect" in DoxygenDocstrings().check(path)[0]
        path.write_text("def broken(\n")
        assert "cannot inspect" in DoxygenDocstrings().check(path)[0]

    def test_report_blocks_missing_docs_and_respects_exclusions(
        self, tmp_path, capsys
    ):
        """!
        @brief Fail missing docs while respecting file exclusions.
        @param tmp_path Pytest temporary directory for the sample files and
        artifacts.
        @param capsys Pytest capture used to check the printed Python output.
        """
        (tmp_path / "source.py").write_text("VALUE = 1\n")
        (tmp_path / "legacy.py").write_text("not valid Python\n")
        (tmp_path / "artifacts").mkdir()
        (tmp_path / "artifacts/generated.py").write_text("invalid\n")
        source = ProjectSource(tmp_path)
        source.exclusions = ["legacy.py"]
        with CheckOutput(tmp_path, verbose=True) as output:
            notes = DoxygenDocstrings().run(source, output)
            assert output.failures == ["Docs"]
        assert "1 issues" in notes[0]
        assert "source.py:1:" in capsys.readouterr().out
        assert "exception fields" in notes[-1]

"""!
@brief Doxygen docstring checks for Python files.
"""

import ast
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from sil_test_quality.output import CheckOutput
from sil_test_quality.reports.diagnostics import DiagnosticReport
from sil_test_quality.source import ProjectSource


class DoxygenDocstrings:
    """!
    @brief Check documentation tags against the Python definitions.
    @details Reads source without importing it. Checks the marker, required text
    and parameter/return tags. Does not generate Doxygen pages.
    """

    DEFINITIONS = (
        ast.Module,
        ast.ClassDef,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
    )
    FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
    TAG = re.compile(r"^\s*[@\\](\w+)(.*)$")
    PARAM = re.compile(
        r"^(?:\[(?:in|out|in\s*,\s*out)\]\s*)?(\*{0,2}\w+)\s+(.+)$"
    )

    def run(self, source: ProjectSource, output: CheckOutput) -> list[str]:
        """!
        @brief Check the repo docstrings and report missing information.
        @param source ProjectSource providing the repo files and exclusions to
        check.
        @param output Report recorder receiving this check's evidence and
        results.
        @return Summary strings describing the rules checked and issue count.
        The Docs verdict is recorded through output.
        """
        output.start("Docs")
        problems: list[str] = []
        for path in source.files():
            if path.suffix == ".py":
                relative = path.relative_to(source.root)
                problems.extend(
                    f"{relative}:{problem}" for problem in self.check(path)
                )
        output.detail('- Docstrings: """! with a nonempty @brief')
        output.detail("- Parameters: signature names and descriptions")
        output.detail("- Returns: documentation for returned or yielded values")
        output.detail("- Tags: populated fields - no TODO or FIXME entries")
        full, normal = DiagnosticReport().render("\n".join(problems))
        output.detail(full, normal=normal)
        output.detail(f"- Documentation issues: {len(problems)}")
        output.result("Docs", not problems)
        return [
            f"Doxygen docstring policy: {len(problems)} issues",
            "Docstrings: modules, classes and functions, including private "
            "helpers and tests. Empty modules are omitted.",
            "Checks: opening marker, @brief, argument names, return "
            "documentation, exception fields and TODO/FIXME entries.",
        ]

    def check(self, path: Path) -> list[str]:
        """!
        @brief Check documentation in one Python file.
        @param path Source file to inspect without executing its code.
        @return Problem messages with lines and definition names. Empty when
        documentation passes.
        """
        try:
            with tokenize.open(path) as stream:
                content = stream.read()
            tree = ast.parse(content)
        except (OSError, SyntaxError, UnicodeError) as error:
            return [f"1: cannot inspect docstrings: {error}"]
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        problems: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, self.DEFINITIONS) or not node.body:
                continue
            location = getattr(node, "lineno", 1)
            name = getattr(node, "name", "module")
            for problem in self.definition(node, parents.get(node), content):
                problems.append(f"{location}: {name}: {problem}")
        return problems

    def definition(
        self,
        node: ast.Module
        | ast.ClassDef
        | ast.FunctionDef
        | ast.AsyncFunctionDef,
        parent: ast.AST | None,
        content: str,
    ) -> list[str]:
        """!
        @brief Check the docstring on a module, class or function.
        @param node Parsed definition providing the docstring and function
        signature.
        @param parent Containing structure used to recognize methods. None for
        the module.
        @param content Original source text used to check the literal Doxygen
        marker.
        @return Problems for this definition, before check adds its name and
        line number.
        """
        document = ast.get_docstring(node, clean=False)
        if document is None:
            return ['missing Doxygen docstring (use """! and @brief)']
        literal = ast.get_source_segment(
            content, cast(ast.Expr, node.body[0]).value
        )
        if not re.match(r'(?:[rRuU])?"""!', literal or ""):
            return ['docstring must start with """!']
        fields = self.fields(document[1:])
        problems = self.field_errors(document, fields)
        if isinstance(node, self.FUNCTIONS):
            problems += self.parameters(node, parent, fields.get("param", []))
            returns = fields.get("return", []) + fields.get("returns", [])
            if self.returns_value(node) and not any(returns):
                problems.append(
                    "document returned or yielded values with @return"
                )
            if len(returns) > 1:
                problems.append("provide only one @return or @returns")
        return problems

    @staticmethod
    def field_errors(document: str, fields: dict[str, list[str]]) -> list[str]:
        """!
        @brief Check required tag text and reject incomplete fields.
        @param document Full docstring text checked for unfinished work.
        @param fields Tag descriptions collected by fields, used to check
        required text.
        @return Messages about invalid or incomplete fields. Empty when these
        checks pass.
        """
        problems: list[str] = []
        if len(fields.get("brief", [])) != 1 or not fields["brief"][0]:
            problems.append("provide one nonempty @brief")
        if re.search(r"\b(TODO|FIXME)\b", document, re.I):
            problems.append("unfinished documentation")
        for tag in (
            "details",
            "note",
            "warning",
            "pre",
            "post",
            "return",
            "returns",
        ):
            if any(not value for value in fields.get(tag, [])):
                problems.append(f"empty @{tag}")
        for tag in ("throws", "throw", "exception"):
            for value in fields.get(tag, []):
                if len(value.split(maxsplit=1)) != 2:
                    problems.append(
                        f"@{tag} needs an exception and description"
                    )
        return problems

    def fields(self, document: str) -> dict[str, list[str]]:
        """!
        @brief Separate Doxygen tags from their descriptions.
        @details Continued lines stay with their tag. Tags inside code/verbatim
        examples are ignored so they do not count as real documentation.
        @param document Docstring text with the initial exclamation mark
        removed.
        @return Dictionary of tag names and description lists, preserving
        repeated tags.
        """
        fields: dict[str, list[str]] = {}
        current = None
        literal = None
        for line in document.splitlines():
            match = self.TAG.match(line)
            if literal:
                if match and match[1] == literal:
                    literal = None
                continue
            if match and match[1] in {"code", "verbatim"}:
                literal = "end" + match[1]
                current = None
            elif match:
                current = fields.setdefault(match[1], [])
                current.append(match[2].strip())
            elif current is not None and line.strip():
                current[-1] = (current[-1] + " " + line.strip()).strip()
        return fields

    def parameters(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent: ast.AST | None,
        fields: list[str],
    ) -> list[str]:
        """!
        @brief Check parameter tags against the function inputs.
        @param node Parsed function whose signature supplies the expected input
        names.
        @param parent Containing structure used to recognize automatic self/cls
        arguments.
        @param fields Descriptions from this function's parameter tags to match
        against inputs.
        @return Messages for missing, repeated or incorrect parameter entries.
        """
        expected = self.arguments(node, parent)
        documented = []
        problems: list[str] = []
        for value in fields:
            match = self.PARAM.fullmatch(value)
            if not match:
                problems.append("@param needs a name and description")
                continue
            name = match[1].lstrip("*")
            if name in documented:
                problems.append(f"duplicate @param {name}")
            documented.append(name)
            if name not in expected:
                problems.append(f"unexpected @param {name}")
        for name in expected:
            if name not in documented:
                problems.append(f"missing @param {name}")
        return problems

    def arguments(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        parent: ast.AST | None,
    ) -> list[str]:
        """!
        @brief Find the input names that need parameter tags.
        @param node Parsed function containing positional, keyword and variadic
        inputs.
        @param parent Containing structure used to distinguish methods from
        functions.
        @return Input names to document, excluding automatic self/cls on bound
        methods.
        """
        args = node.args
        positional = [*args.posonlyargs, *args.args]
        decorators = {ast.unparse(item) for item in node.decorator_list}
        bound = (
            isinstance(parent, ast.ClassDef)
            and "staticmethod" not in decorators
        )
        if bound and positional and positional[0].arg in {"self", "cls"}:
            positional = positional[1:]
        arguments = [*positional, *args.kwonlyargs]
        arguments += [item for item in (args.vararg, args.kwarg) if item]
        return [item.arg for item in arguments]

    def returns_value(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> bool:
        """!
        @brief Decide whether a function needs a return tag.
        @param node Parsed function whose annotation and body describe its
        return behavior.
        @return True when a returned or yielded value needs documenting. False
        otherwise.
        """
        body = list(self.body(node))
        if any(isinstance(item, (ast.Yield, ast.YieldFrom)) for item in body):
            return True
        if node.returns is not None:
            annotation = ast.unparse(node.returns).strip("'\"")
            return annotation not in {
                "None",
                "NoReturn",
                "Never",
                "typing.NoReturn",
                "typing.Never",
            }
        for item in body:
            if isinstance(item, ast.Return) and item.value is not None:
                if (
                    not isinstance(item.value, ast.Constant)
                    or item.value.value is not None
                ):
                    return True
        return False

    def body(self, node: ast.AST) -> Iterator[ast.AST]:
        """!
        @brief Inspect a function body without entering nested functions.
        @param node Function or contained expression being inspected for
        return/yield behavior.
        @return Contained syntax nodes for returns_value, skipping nested
        definitions and lambdas.
        """
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, (*self.DEFINITIONS, ast.Lambda)):
                yield child
                yield from self.body(child)

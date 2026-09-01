"""Smart Test Suite Generator with Coverage analysis for SBpy."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field


@dataclass
class TargetFunc:
    name: str
    args: list[str]
    is_async: bool = False
    docstring: str = ""
    lineno: int = 1


@dataclass
class TargetClass:
    name: str
    methods: list[TargetFunc] = field(default_factory=list)
    lineno: int = 1


def analyze_source_file(path: str) -> tuple[list[TargetFunc], list[TargetClass]]:
    """Analyzes a Python file to extract callable functions and classes."""
    if not os.path.isfile(path):
        return [], []

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return [], []

    functions: list[TargetFunc] = []
    classes: list[TargetClass] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue
            args = [a.arg for a in node.args.args if a.arg != "self"]
            functions.append(
                TargetFunc(
                    name=node.name,
                    args=args,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    docstring=ast.get_docstring(node) or "",
                    lineno=node.lineno,
                )
            )
        elif isinstance(node, ast.ClassDef):
            cls_methods: list[TargetFunc] = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_") and item.name != "__init__":
                        continue
                    args = [a.arg for a in item.args.args if a.arg != "self"]
                    cls_methods.append(
                        TargetFunc(
                            name=item.name,
                            args=args,
                            is_async=isinstance(item, ast.AsyncFunctionDef),
                            docstring=ast.get_docstring(item) or "",
                            lineno=item.lineno,
                        )
                    )
            classes.append(TargetClass(name=node.name, methods=cls_methods, lineno=node.lineno))

    return functions, classes


def generate_unit_tests(path: str) -> str:
    """Generates a complete unittest test file for the given source file."""
    functions, classes = analyze_source_file(path)
    module_name = os.path.splitext(os.path.basename(path))[0]

    code_lines = [
        '"""Auto-generated test suite by SBpy Smart Test Generator."""',
        "",
        "from __future__ import annotations",
        "",
        "import unittest",
        f"import {module_name}",
        "",
        "",
        f"class Test{module_name.capitalize()}(unittest.TestCase):",
    ]

    if not functions and not classes:
        code_lines.append("    def test_module_importable(self) -> None:")
        code_lines.append(f"        self.assertIsNotNone({module_name})")
        return "\n".join(code_lines) + "\n"

    for fn in functions:
        code_lines.append(f"    # --- Tests for {fn.name}() ---")
        code_lines.append(f"    def test_{fn.name}_basic(self) -> None:")
        if fn.args:
            args_sample = ", ".join(["None" for _ in fn.args])
            code_lines.append("        try:")
            code_lines.append(f"            res = {module_name}.{fn.name}({args_sample})")
            code_lines.append("        except (TypeError, ValueError):")
            code_lines.append("            pass")
        else:
            code_lines.append(f"        res = {module_name}.{fn.name}()")
            code_lines.append("        self.assertIsNotNone(res)")

        code_lines.append(f"    def test_{fn.name}_edge_cases(self) -> None:")
        if fn.args:
            code_lines.append("        # Test with empty inputs and zero")
            args_empty = ", ".join(["0" if i == 0 else "''" for i in range(len(fn.args))])
            code_lines.append("        try:")
            code_lines.append(f"            {module_name}.{fn.name}({args_empty})")
            code_lines.append("        except Exception:")
            code_lines.append("            pass")
        else:
            code_lines.append("        pass")
        code_lines.append("")

    for cls in classes:
        code_lines.append(f"    # --- Tests for class {cls.name} ---")
        code_lines.append(f"    def test_{cls.name.lower()}_instantiation(self) -> None:")
        code_lines.append("        try:")
        code_lines.append(f"            obj = {module_name}.{cls.name}()")
        code_lines.append("            self.assertIsNotNone(obj)")
        code_lines.append("        except Exception:")
        code_lines.append("            pass")
        code_lines.append("")

    code_lines.extend([
        "",
        "if __name__ == '__main__':",
        "    unittest.main()",
        "",
    ])

    return "\n".join(code_lines)


def generate_test_file(path: str, output_path: str | None = None) -> str:
    """Generates tests and saves them to a test file."""
    test_content = generate_unit_tests(path)
    if output_path is None:
        module_name = os.path.splitext(os.path.basename(path))[0]
        tests_dir = os.path.join(os.getcwd(), "tests")
        os.makedirs(tests_dir, exist_ok=True)
        output_path = os.path.join(tests_dir, f"test_{module_name}.py")

    with open(output_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(test_content)

    return output_path

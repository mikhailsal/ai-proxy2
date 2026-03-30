from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE_LINE_LIMIT = 500
PYTHON_FUNCTION_LINE_LIMIT = 60
CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}
FILE_EXCLUDES = {
    ".git",
    ".venv",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "__pycache__",
}
PYTHON_FUNCTION_EXCLUDES = {
    "backend/migrations/versions",
}


def iter_code_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in CODE_EXTENSIONS:
            continue
        if any(part in FILE_EXCLUDES for part in path.relative_to(ROOT).parts):
            continue
        files.append(path)
    return sorted(files)


def check_file_sizes(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > FILE_LINE_LIMIT:
            rel_path = path.relative_to(ROOT).as_posix()
            errors.append(
                f"{rel_path}: file has {line_count} lines; limit is {FILE_LINE_LIMIT}"
            )
    return errors


def is_function_excluded(path: Path) -> bool:
    rel_path = path.relative_to(ROOT).as_posix()
    return any(rel_path.startswith(prefix) for prefix in PYTHON_FUNCTION_EXCLUDES)


def check_python_function_sizes(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        if path.suffix != ".py" or is_function_excluded(path):
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            end_lineno = getattr(node, "end_lineno", None)
            if end_lineno is None:
                continue
            line_count = end_lineno - node.lineno + 1
            if line_count > PYTHON_FUNCTION_LINE_LIMIT:
                rel_path = path.relative_to(ROOT).as_posix()
                errors.append(
                    f"{rel_path}:{node.lineno} {node.name} has {line_count} lines; "
                    f"limit is {PYTHON_FUNCTION_LINE_LIMIT}"
                )
    return errors


def main() -> int:
    files = iter_code_files()
    errors = [
        *check_file_sizes(files),
        *check_python_function_sizes(files),
    ]
    if not errors:
        print("Code size checks passed.")
        return 0

    print("Code size checks failed:")
    for error in errors:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

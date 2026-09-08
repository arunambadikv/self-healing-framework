"""Extract exact locator return expressions from page source files."""

from __future__ import annotations

import ast
from pathlib import Path


def resolve_page_path(workspace: Path, file_ref: str) -> Path:
    """Resolve a manifest or patch file reference to an absolute page path."""
    path = Path(file_ref)
    if path.is_absolute():
        return path
    return (workspace / path).resolve()


def extract_property_return_expression(source: str, symbol: str) -> str | None:
    """Return the exact `return` expression for `@property def symbol` in source text."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef) or item.name != symbol:
                continue
            if not any(
                isinstance(d, ast.Name) and d.id == "property"
                for d in item.decorator_list
            ):
                continue
            for child in ast.walk(item):
                if isinstance(child, ast.Return) and child.value is not None:
                    segment = ast.get_source_segment(source, child.value)
                    if segment:
                        return segment.strip()
                    try:
                        return ast.unparse(child.value)
                    except Exception:
                        return None
    return None


def read_property_return_expression(path: Path, symbol: str) -> str | None:
    """Read a page file and return the exact return expression for a locator property."""
    if not path.is_file():
        return None
    return extract_property_return_expression(path.read_text(encoding="utf-8"), symbol)

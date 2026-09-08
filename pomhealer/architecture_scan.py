"""Scan pages/, tests/, data/ and build architecture manifest."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pomhealer.paths import MANIFEST_JSON, MANIFEST_MD, ARCHITECTURE_DIR, ensure_queue_dirs

SCAN_DIRS = ("pages", "tests", "data")


def _file_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        if path.is_file():
            digest.update(str(path).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _locator_expression_from_function(source: str, node: ast.FunctionDef) -> str:
    for child in ast.walk(node):
        if isinstance(child, ast.Return) and child.value is not None:
            segment = ast.get_source_segment(source, child.value)
            if segment:
                return segment.strip()
            try:
                return ast.unparse(child.value)
            except Exception:
                return "<dynamic>"
    return ""


def _scan_page_file(path: Path, workspace: Path) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    try:
        rel_file = str(path.resolve().relative_to(workspace.resolve()).as_posix())
    except ValueError:
        rel_file = str(path.as_posix())
    classes: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        locators: dict[str, Any] = {}
        methods: dict[str, Any] = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name.startswith("_") and item.name != "__init__":
                    continue
                if any(
                    isinstance(d, ast.Name) and d.id == "property"
                    for d in getattr(item, "decorator_list", [])
                ):
                    locators[item.name] = {
                        "line": item.lineno,
                        "kind": "property",
                        "expression": _locator_expression_from_function(source, item),
                    }
                elif not item.name.startswith("__"):
                    methods[item.name] = {
                        "line": item.lineno,
                        "locator_deps": _infer_locator_deps(item),
                    }
        classes[node.name] = {
            "file": rel_file,
            "locators": locators,
            "methods": methods,
        }
    return classes


def _infer_locator_deps(func: ast.FunctionDef) -> list[str]:
    deps: list[str] = []
    source = ast.unparse(func)
    for match in re.finditer(r"self\.(\w+)", source):
        name = match.group(1)
        if name not in ("page", "base_url", "page_class") and not name.startswith("_"):
            deps.append(name)
    return sorted(set(deps))


def _scan_test_file(path: Path, workspace: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    pages = sorted(set(re.findall(r"(\w+Page)\s*\(", text)))
    skip_fixtures = frozenset(
        {"self", "page", "path", "re", "json", "pytest", "os", "sys", "print", "open"}
    )
    call_pairs = re.findall(r"\b([a-z][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\s*\(", text)
    calls = sorted(
        {
            f"{fixture}.{method}"
            for fixture, method in call_pairs
            if fixture not in skip_fixtures and not fixture.startswith("_")
        }
    )
    try:
        rel_file = str(path.resolve().relative_to(workspace.resolve()).as_posix())
    except ValueError:
        rel_file = str(path.as_posix())
    return {
        "file": rel_file,
        "page_classes": pages,
        "page_method_calls": calls,
    }


def build_manifest(workspace: Path) -> dict[str, Any]:
    from pomhealer.config import load_config
    from pomhealer.paths import configure_workspace

    configure_workspace(workspace)
    cfg = load_config(workspace)

    paths: list[Path] = []
    pages: dict[str, Any] = {}
    pages_dir = workspace / cfg.pages_dir
    if pages_dir.exists():
        for page_file in sorted(pages_dir.glob("*.py")):
            if page_file.name.startswith("_") or page_file.name == "__init__.py":
                continue
            paths.append(page_file)
            pages.update(_scan_page_file(page_file, workspace))

    tests: list[dict[str, Any]] = []
    tests_dir = workspace / cfg.tests_dir
    if tests_dir.exists():
        for test_file in sorted(tests_dir.glob("test_*.py")):
            paths.append(test_file)
            tests.append(_scan_test_file(test_file, workspace))

    data_files: list[str] = []
    data_dir = workspace / cfg.data_dir
    if data_dir.exists():
        for data_file in sorted(data_dir.rglob("*")):
            if data_file.is_file():
                paths.append(data_file)
                data_files.append(str(data_file.relative_to(workspace).as_posix()))

    content_hash = _file_hash(paths)
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": content_hash,
        "pages": pages,
        "tests": tests,
        "data_files": data_files,
    }


def manifest_to_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Architecture Manifest",
        "",
        f"**Generated:** {manifest.get('generated_at')}",
        f"**Content hash:** `{manifest.get('content_hash')}`",
        "",
        "## Pages",
        "",
    ]
    for class_name, info in manifest.get("pages", {}).items():
        lines.append(f"### {class_name} (`{info.get('file')}`)")
        lines.append("")
        lines.append("**Locators:**")
        for loc_id, loc in info.get("locators", {}).items():
            lines.append(f"- `{loc_id}` (line {loc.get('line')}): `{loc.get('expression', '')[:80]}`")
        lines.append("")
        lines.append("**Methods:**")
        for method, meta in info.get("methods", {}).items():
            deps = ", ".join(meta.get("locator_deps") or [])
            lines.append(f"- `{method}` (line {meta.get('line')}) → {deps or '—'}")
        lines.append("")
    lines.append("## Tests")
    lines.append("")
    for test in manifest.get("tests", []):
        lines.append(f"- `{test.get('file')}` — pages: {test.get('page_classes')}, calls: {test.get('page_method_calls')}")
    if manifest.get("data_files"):
        lines.extend(["", "## Data files", ""] + [f"- `{f}`" for f in manifest["data_files"]])
    return "\n".join(lines)


def write_manifest(manifest: dict[str, Any], workspace: Path) -> tuple[Path, Path, bool]:
    ensure_queue_dirs()
    changed = True
    if MANIFEST_JSON.exists():
        try:
            old = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
            if old.get("content_hash") == manifest.get("content_hash"):
                changed = False
        except json.JSONDecodeError:
            pass
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8")
    MANIFEST_MD.write_text(manifest_to_markdown(manifest), encoding="utf-8")
    return MANIFEST_JSON, MANIFEST_MD, changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Build architecture manifest for POM pomhealer.")
    parser.add_argument("--workspace", default=".", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if manifest missing or stale vs current scan.",
    )
    args = parser.parse_args()
    from pomhealer.paths import configure_workspace

    workspace = configure_workspace(args.workspace.resolve())
    manifest = build_manifest(workspace)
    if args.check:
        if not MANIFEST_JSON.exists():
            print(f"Missing manifest: {MANIFEST_JSON}")
            return 1
        old = json.loads(MANIFEST_JSON.read_text(encoding="utf-8"))
        if old.get("content_hash") != manifest.get("content_hash"):
            print("Architecture manifest is stale. Run: python -m pomhealer.architecture_scan")
            return 1
        print("Architecture manifest is up to date.")
        return 0
    json_path, md_path, changed = write_manifest(manifest, workspace)
    from pomhealer.auto_scan import write_package_version_stamp

    write_package_version_stamp()
    if changed:
        print(f"Wrote {json_path} and {md_path}")
    else:
        print(f"Manifest up to date ({manifest['content_hash']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

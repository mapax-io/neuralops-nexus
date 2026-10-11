"""
T16 — the dependency rules, checked statically (§1.5 rules):

  1. nothing under ai_engine/ imports fastapi or django; its only fastapi_app
     import is fastapi_app.contracts (plus the bare package whose __init__ is empty)
  2. only ai_engine/pydantic_ai_system/ imports pydantic_ai / pydantic_ai_harness
  3. nothing imports from the legacy module (modules/nexus-ai-legacy, package root `apps`)
  4. fastapi_app/__init__.py stays empty of imports — ai_engine pulls
     fastapi_app.contracts in, and anything imported there would come with it
"""
from __future__ import annotations

import ast
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parent.parent


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def _py_files(package: str) -> list[Path]:
    return sorted((MODULE_ROOT / package).rglob("*.py"))


def test_t16_ai_engine_is_framework_free():
    for path in _py_files("ai_engine"):
        for name in _imports(path):
            root = name.split(".")[0]
            assert root not in ("fastapi", "django", "starlette"), f"{path} imports {name}"
            if root == "fastapi_app":
                assert name.startswith("fastapi_app.contracts"), \
                    f"{path} imports {name} — ai_engine may import only fastapi_app.contracts"


def test_t16_only_pydantic_ai_system_imports_the_framework():
    for path in _py_files("ai_engine") + _py_files("fastapi_app"):
        inside = "pydantic_ai_system" in path.parts
        for name in _imports(path):
            root = name.split(".")[0]
            if root in ("pydantic_ai", "pydantic_ai_harness"):
                assert inside, f"{path} imports {name} outside ai_engine/pydantic_ai_system/"


def test_t16_nothing_imports_the_legacy_module():
    for path in _py_files("ai_engine") + _py_files("fastapi_app"):
        for name in _imports(path):
            root = name.split(".")[0]
            assert root != "apps", f"{path} imports the legacy module ({name})"
            assert "nexus_ai_legacy" not in name and "nexus-ai-legacy" not in name


def test_t16_fastapi_app_init_is_empty_of_imports():
    assert _imports(MODULE_ROOT / "fastapi_app" / "__init__.py") == []

"""
Guards the pdfnik-schemes pin against the failure that took the whole stack
down: main_app imports a module or name from pdfnik_contracts that the
*pinned* revision does not contain, so the container dies at import with
ModuleNotFoundError while every local test stays green.

Why the existing suite was blind to it: the uv workspace maps
pdfnik-schemes to the sibling PDFnik-Schemes source
(`[tool.uv.sources] pdfnik-schemes = { workspace = true }`), so pytest always
sees the newest contracts. Docker does not use the workspace - it runs
`uv pip install -r requirements.txt` and gets whatever git revision is
pinned there. The two drifted apart and only the container noticed.

The checks below inspect the pinned revision inside the sibling
PDFnik-Schemes clone through git, so they stay offline and deterministic.
They skip when that clone is absent (single-repo CI checkout).

Deliberately duplicated in PDFnik-Backend and PDFnik-TelegramBot instead of
shared: the two services are separate repositories that must not import each
other (.claude/rules/architecture.md), and the contracts package may hold
models and constants only - there is nowhere to put a common helper.
"""

import ast
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

SERVICE_ROOT = Path(__file__).resolve().parents[2]
SCHEMES_REPO = SERVICE_ROOT.parent / "PDFnik-Schemes"
CONTRACTS_PACKAGE = "pdfnik_contracts"

_GIT_TIMEOUT_SEC = 15

# `pdfnik-schemes @ git+https://.../PDFnik-Schemes@<rev>` in pyproject.toml
# and in the uv-compiled requirements.txt.
_PIN_RE = re.compile(r"pdfnik-schemes\s*@\s*git\+[^@\s]+@(?P<rev>[^\s\"',]+)")


class ContractImport(BaseModel):
    """One `from pdfnik_contracts.<module> import <names>` found in main_app/."""

    model_config = ConfigDict(frozen=True)

    module: str
    names: tuple[str, ...]
    source_file: str


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(SCHEMES_REPO), *args],  # fixed argv, no shell
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT_SEC,
        check=True,
    )
    return result.stdout


def _skip_unless_schemes_clone_available() -> None:
    if not (SCHEMES_REPO / ".git").exists():
        pytest.skip(f"PDFnik-Schemes clone not found next to the service: {SCHEMES_REPO}")


def _resolve_rev(rev: str) -> str:
    """Full commit sha for a tag/sha pin, or skip when the clone is stale."""
    try:
        return _git("rev-parse", f"{rev}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        pytest.skip(
            f"revision {rev!r} is unknown to the local PDFnik-Schemes clone - "
            f"run `git -C {SCHEMES_REPO} fetch --tags` and re-run"
        )


def _read_pin(path: Path) -> str:
    match = _PIN_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        pytest.fail(f"no pdfnik-schemes git pin found in {path.name}")
    return match.group("rev")


def _top_level_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _collect_contract_imports() -> list[ContractImport]:
    imports: list[ContractImport] = []
    for py_file in sorted((SERVICE_ROOT / "main_app").rglob("*.py")):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or not node.module.startswith(f"{CONTRACTS_PACKAGE}."):
                continue
            imports.append(
                ContractImport(
                    module=node.module.split(".", 1)[1],
                    names=tuple(alias.name for alias in node.names),
                    source_file=py_file.relative_to(SERVICE_ROOT).as_posix(),
                )
            )
    return imports


CONTRACT_IMPORTS = _collect_contract_imports()


def test_main_app_imports_at_least_one_contract_module() -> None:
    """Without this the parametrized check below could pass vacuously."""
    assert CONTRACT_IMPORTS, "no pdfnik_contracts imports collected - is the collector broken?"


def test_pyproject_and_requirements_pin_the_same_schemes_revision() -> None:
    """
    pyproject.toml pins a tag, requirements.txt pins the sha uv resolved it to.
    A bump that touches only one of the two files ships a container built
    against different contracts than the ones declared.
    """
    _skip_unless_schemes_clone_available()

    declared = _read_pin(SERVICE_ROOT / "pyproject.toml")
    locked = _read_pin(SERVICE_ROOT / "requirements.txt")

    assert _resolve_rev(declared) == _resolve_rev(locked), (
        f"pyproject.toml pins {declared!r} but requirements.txt pins {locked!r} - "
        f"re-run `uv pip compile pyproject.toml --no-sources -o requirements.txt`"
    )


def test_pinned_schemes_revision_matches_the_workspace_source() -> None:
    """
    Tests run against the workspace source, the container runs against the pin.
    When the workspace version is ahead, every test here is validating code
    that will not be installed in production.
    """
    _skip_unless_schemes_clone_available()

    pinned_rev = _resolve_rev(_read_pin(SERVICE_ROOT / "pyproject.toml"))
    pinned_version = tomllib.loads(_git("show", f"{pinned_rev}:pyproject.toml"))["project"][
        "version"
    ]
    workspace_version = tomllib.loads(
        (SCHEMES_REPO / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]

    assert pinned_version == workspace_version, (
        f"pdfnik-schemes pin is at version {pinned_version}, but the workspace "
        f"source is at {workspace_version} - bump, tag and push PDFnik-Schemes, "
        f"then update the pin in pyproject.toml and requirements.txt"
    )


@pytest.mark.parametrize(
    "contract_import",
    CONTRACT_IMPORTS,
    ids=[f"{ci.source_file}::{ci.module}" for ci in CONTRACT_IMPORTS],
)
def test_pinned_schemes_revision_defines_every_imported_name(
    contract_import: ContractImport,
) -> None:
    _skip_unless_schemes_clone_available()

    pinned_rev = _resolve_rev(_read_pin(SERVICE_ROOT / "pyproject.toml"))
    module_path = f"{CONTRACTS_PACKAGE}/{contract_import.module}.py"

    try:
        source = _git("show", f"{pinned_rev}:{module_path}")
    except subprocess.CalledProcessError:
        pytest.fail(
            f"{contract_import.source_file} imports {contract_import.module!r}, "
            f"but the pinned pdfnik-schemes revision has no {module_path} - "
            f"the container will die with ModuleNotFoundError at import"
        )

    missing = sorted(set(contract_import.names) - _top_level_names(source))
    assert not missing, (
        f"{contract_import.source_file} imports {missing} from {contract_import.module!r}, "
        f"but the pinned pdfnik-schemes revision does not define them"
    )

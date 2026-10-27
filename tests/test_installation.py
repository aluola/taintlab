"""Exercise the actual PowerShell installer in isolated roots; never touch services.

Interpreter/venv creation is real. Package-manager invocations are controlled
fixtures so these regressions cannot download or modify the working environment.
The publication acceptance separately installs the real locked dependencies.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell installer")


@pytest.fixture
def install_root(tmp_path):
    root = tmp_path / "新目录 fresh root with spaces"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/install.ps1", root / "scripts/install.ps1")
    (root / "requirements.lock.txt").write_text("# isolated fixture\n", encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname="fixture"\nversion="0.0.0"\n', encoding="utf-8")
    # -m pip resolves this test fixture from cwd. No network or package install.
    (root / "pip.py").write_text(
        "import json,os,pathlib,sys\n"
        "with pathlib.Path(os.environ['INSTALL_TEST_LOG']).open('a') as f: f.write(json.dumps(['pip']+sys.argv[1:])+'\\n')\n"
        "sys.exit(int(os.environ.get('INSTALL_TEST_PIP_EXIT','0')))\n", encoding="utf-8"
    )
    return root


UV_FIXTURE = r"""
function uv {
    $callArguments = @($args)
    ConvertTo-Json -Compress -InputObject (@('uv') + $callArguments) | Add-Content -LiteralPath $env:INSTALL_TEST_LOG -Encoding UTF8
    if ($callArguments[0] -eq 'venv') {
        & $env:INSTALL_TEST_BASE_PYTHON -m venv --without-pip $callArguments[-1]
        $global:LASTEXITCODE = $LASTEXITCODE
    } elseif ($callArguments[1] -eq 'install' -and $callArguments -contains '-r') {
        $global:LASTEXITCODE = [int]$env:INSTALL_TEST_PIP_EXIT
    } else {$global:LASTEXITCODE = 0}
}
"""
PY_FIXTURE = r"""
function py {
    $callArguments = @($args)
    if ($callArguments[0] -ne '-3.12') {throw 'Fixture requires explicit 3.12'}
    $remaining = @($callArguments | Select-Object -Skip 1)
    & $env:INSTALL_TEST_BASE_PYTHON @remaining
    $global:LASTEXITCODE = $LASTEXITCODE
}
"""
PYTHON_FIXTURE = r"""
function python {
    & $env:INSTALL_TEST_BASE_PYTHON @args
    $global:LASTEXITCODE = $LASTEXITCODE
}
"""


def run_install(root, definitions="", *, failure=0, venv=".venv"):
    wrapper = root / "invoke_fixture.ps1"
    wrapper.write_text(
        "$ErrorActionPreference='Stop'\n[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n" + definitions +
        "\n& (Join-Path $PSScriptRoot 'scripts/install.ps1') -Venv $env:INSTALL_TEST_VENV\n", encoding="utf-8"
    )
    env = dict(os.environ)
    env.update(
        PATH=str(POWERSHELL.parent),  # hide host uv/py/python; use only defined fixtures
        INSTALL_TEST_BASE_PYTHON=sys._base_executable,
        INSTALL_TEST_LOG=str(root / "calls.jsonl"),
        INSTALL_TEST_PIP_EXIT=str(failure),
        INSTALL_TEST_VENV=venv,
        PYTHONUTF8="1",
        PIP_NO_INDEX="1",
        UV_OFFLINE="1",
    )
    result = subprocess.run(
        [str(POWERSHELL), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(wrapper)],
        cwd=root.parent, env=env, capture_output=True, timeout=90,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    result.output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    log = root / "calls.jsonl"
    calls = [json.loads(line) for line in log.read_text("utf-8-sig").splitlines()] if log.exists() else []
    return result, calls


def test_fresh_uv_install_handles_space_path_and_checks_dependencies(install_root):
    result, calls = run_install(install_root, UV_FIXTURE)
    assert result.returncode == 0, result.output
    assert (install_root / ".venv/Scripts/python.exe").is_file()
    assert calls[0][:4] == ["uv", "venv", "--python", "3.12"]
    assert calls[0][-1] == str(install_root / ".venv")
    assert len(calls) == 4
    assert "--no-deps" in calls[2] and "--no-build-isolation" in calls[2]
    assert calls[-1][:3] == ["uv", "pip", "check"]


def test_repeat_install_reuses_venv_and_preserves_user_files(install_root):
    first, calls = run_install(install_root, UV_FIXTURE)
    assert first.returncode == 0, first.output
    sentinel = install_root / ".venv/user-sentinel.txt"
    sentinel.write_text("do not remove", encoding="utf-8")
    second, repeated = run_install(install_root, UV_FIXTURE)
    assert second.returncode == 0, second.output
    assert len([call for call in repeated if call[:2] == ["uv", "venv"]]) == 1
    assert sentinel.read_text("utf-8") == "do not remove"
    assert "Reusing verified" in second.output


def test_partial_target_is_not_cleared(install_root):
    directory = install_root / ".venv"
    directory.mkdir()
    sentinel = directory / "valuable.txt"
    sentinel.write_text("preserved", encoding="utf-8")
    result, calls = run_install(install_root, UV_FIXTURE)
    assert result.returncode != 0
    assert "no existing files were removed" in result.output
    assert sentinel.read_text("utf-8") == "preserved" and calls == []


@pytest.mark.parametrize("launcher", [PY_FIXTURE, PYTHON_FIXTURE], ids=["windows-py", "python-on-path"])
def test_without_uv_accepts_supported_python_discovery(install_root, launcher):
    result, calls = run_install(install_root, launcher)
    assert result.returncode == 0, result.output
    assert (install_root / ".venv/pyvenv.cfg").is_file()
    assert calls[0] == ["pip", "install", "-r", "requirements.lock.txt"]
    assert calls[-1] == ["pip", "check"]


def test_missing_python_has_actionable_error_without_creating_environment(install_root):
    result, calls = run_install(install_root)
    assert result.returncode != 0
    assert "Python 3.12 x64 was not found" in result.output
    assert not (install_root / ".venv").exists() and calls == []


def test_wrong_python_is_rejected_before_environment_creation(install_root):
    result, calls = run_install(install_root, "function python {$global:LASTEXITCODE=1}")
    assert result.returncode != 0
    assert "Python 3.12 x64 was not found" in result.output
    assert not (install_root / ".venv").exists() and calls == []


def test_failed_locked_install_cannot_continue_to_editable_install(install_root):
    result, calls = run_install(install_root, UV_FIXTURE, failure=23)
    assert result.returncode != 0
    assert "Locked dependency installation failed" in result.output
    assert len(calls) == 2 and not any("-e" in call for call in calls)

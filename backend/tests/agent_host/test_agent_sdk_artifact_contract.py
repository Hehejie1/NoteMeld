from __future__ import annotations

import subprocess
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]


def test_source_launcher_installs_and_validates_external_sdk_wheel() -> None:
    source = (ROOT / "run_notemeld.sh").read_text(encoding="utf-8")
    assert "NOTEMELD_AGENT_SDK_WHEEL" in source
    assert "--no-deps --force-reinstall" in source
    assert "import notemeld_agent_sdk.runtime as sdk_runtime" in source
    assert 'SDK_VERSION == "0.1.0"' in source
    assert 'SCHEMA_VERSION == "1"' in source
    assert "Installed notemeld-agent-sdk is incompatible" in source


def test_installed_launcher_keeps_sdk_install_contract() -> None:
    source = (ROOT / "scripts" / "notemeld").read_text(encoding="utf-8")
    assert "NOTEMELD_AGENT_SDK_WHEEL" in source
    assert "ensure_agent_sdk" in source
    assert "import notemeld_agent_sdk.runtime as sdk_runtime" in source
    assert 'SDK_VERSION == "0.1.0"' in source
    assert 'SCHEMA_VERSION == "1"' in source
    assert "Installed notemeld-agent-sdk is incompatible" in source


def test_source_and_installed_launchers_have_valid_shell_syntax() -> None:
    for script in (ROOT / "run_notemeld.sh", ROOT / "scripts" / "notemeld"):
        result = subprocess.run(
            ["bash", "-n", str(script)], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr


def test_cli_supports_model_selection_without_own_agent_runtime() -> None:
    source = (ROOT / "scripts" / "notemeld-agent.py").read_text(encoding="utf-8")
    assert 'parser.add_argument("--model"' in source
    assert 'text.startswith("/model ")' in source
    assert 'payload["model"]' in source
    assert "app.agent.core" not in source


def _ensure_function(script: Path) -> str:
    source = script.read_text(encoding="utf-8")
    match = re.search(r"^ensure_agent_sdk\(\) \{\n.*?^\}\n", source, re.MULTILINE | re.DOTALL)
    assert match, f"ensure_agent_sdk() missing from {script}"
    return match.group(0)


def _run_ensure(script: Path, *, sdk_state: str, wheel: Path | None) -> subprocess.CompletedProcess[str]:
    function = _ensure_function(script)
    with _temporary_launcher_inputs() as inputs:
        app_dir, fake_python, state_file, pip_log = inputs
        env = {
            "FAKE_SDK_STATE": sdk_state,
            "FAKE_SDK_STATE_FILE": str(state_file),
            "FAKE_PIP_LOG": str(pip_log),
        }
        if "VENV_DIR" in function:
            env["VENV_DIR"] = str(app_dir / ".venv")
        else:
            env["APP_DIR"] = str(app_dir)
        if wheel is not None:
            env["NOTEMELD_AGENT_SDK_WHEEL"] = str(wheel)
        harness = f'''#!/usr/bin/env bash
set -euo pipefail
APP_DIR="${{APP_DIR:-}}"
VENV_DIR="${{VENV_DIR:-}}"
NOTEMELD_AGENT_SDK_WHEEL="${{NOTEMELD_AGENT_SDK_WHEEL:-}}"
fail() {{ printf '%s\\n' "$*" >&2; exit 1; }}
log() {{ :; }}
{function}
ensure_agent_sdk
'''
        return subprocess.run(
            ["bash", "-c", harness],
            env={**os.environ, **env},
            text=True,
            capture_output=True,
        )


class _temporary_launcher_inputs:
    def __enter__(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.app_dir = root / "app"
        (self.app_dir / ".venv" / "bin").mkdir(parents=True)
        self.state_file = root / "state"
        self.pip_log = root / "pip.log"
        fake = self.app_dir / ".venv" / "bin" / "python"
        fake.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
if [[ \"$1\" == \"-c\" ]]; then
  state=\"${FAKE_SDK_STATE:-compatible}\"
  if [[ \"$state\" == \"missing_then_compatible\" && -f \"${FAKE_SDK_STATE_FILE}\" ]]; then
    exit 0
  fi
  [[ \"$state\" == \"compatible\" ]] && exit 0
  exit 1
fi
if [[ \"$1\" == \"-m\" && \"$2\" == \"pip\" ]]; then
  printf 'pip\\n' >> \"${FAKE_PIP_LOG}\"
  touch \"${FAKE_SDK_STATE_FILE}\"
  exit 0
fi
exit 99
""",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        self.fake_python = fake
        return self.app_dir, fake, self.state_file, self.pip_log

    def __exit__(self, *_args):
        self._tmp.cleanup()


def test_installed_launcher_skips_pip_when_sdk_versions_match() -> None:
    result = _run_ensure(ROOT / "scripts" / "notemeld", sdk_state="compatible", wheel=None)
    assert result.returncode == 0, result.stderr


def test_source_launcher_installs_missing_sdk_then_revalidates(tmp_path: Path) -> None:
    wheel = tmp_path / "notemeld_agent_sdk-0.1.0.whl"
    wheel.touch()
    result = _run_ensure(ROOT / "run_notemeld.sh", sdk_state="missing_then_compatible", wheel=wheel)
    assert result.returncode == 0, result.stderr


def test_launcher_fails_closed_when_sdk_is_missing_or_incompatible(tmp_path: Path) -> None:
    missing = _run_ensure(ROOT / "scripts" / "notemeld", sdk_state="incompatible", wheel=None)
    assert missing.returncode != 0
    wheel = tmp_path / "notemeld_agent_sdk-0.1.0.whl"
    wheel.touch()
    incompatible = _run_ensure(ROOT / "run_notemeld.sh", sdk_state="incompatible", wheel=wheel)
    assert incompatible.returncode != 0

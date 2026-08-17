from __future__ import annotations

import subprocess
import sys
import textwrap


def test_production_app_import_does_not_load_legacy_agent_core():
    code = textwrap.dedent(
        """
        import sys
        from main import app  # noqa: F401
        legacy = [name for name in sys.modules if name.startswith('app.agent.core')]
        if legacy:
            raise SystemExit('legacy Agent core imported: ' + ','.join(legacy))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd="backend",
        env={"PYTHONPATH": ".", **__import__("os").environ},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout

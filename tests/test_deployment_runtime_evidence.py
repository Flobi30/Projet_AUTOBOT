from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess

import pytest


pytestmark = pytest.mark.unit


_COMMIT = "a" * 40
_TEST_SUBPROCESS_TIMEOUT_SECONDS = 30


def _bash_path(path: Path) -> str:
    """Return a path understood by the local Bash implementation.

    Desktop tests run from Windows through WSL Bash, while CI normally runs
    native POSIX Bash.  Keeping this conversion in the hermetic test avoids
    any dependency on Docker, Git or a VPS.
    """

    resolved = path.resolve()
    if not resolved.drive:
        return str(resolved)
    return f"/mnt/{resolved.drive.rstrip(':').lower()}{resolved.as_posix()[2:]}"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")
    path.chmod(0o755)


def _run_verifier_with_fake_runtime_lock(
    tmp_path: Path,
    *,
    program_locked: bool = True,
    observation_only: bool = True,
    paper_authorized: bool = False,
    real_order_authorized: bool = False,
    final_health_payload: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the verifier against fake local tools, never a real container."""

    root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()

    _write_executable(
        fake_bin / "git",
        f"#!/usr/bin/env bash\nprintf '%s\\n' '{_COMMIT}'\n",
    )
    _write_executable(
        fake_bin / "curl",
        """#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${FAKE_FINAL_HEALTH_PAYLOAD:-}" ]]; then
  if [[ -f "${FAKE_HEALTH_CALL_FILE:?}" ]]; then
    printf '%s\\n' "${FAKE_FINAL_HEALTH_PAYLOAD}"
    exit 0
  fi
  : > "${FAKE_HEALTH_CALL_FILE}"
fi
printf '%s\\n' '{"status":"healthy","components":{"websocket":"connected"}}'
""",
    )
    _write_executable(
        fake_bin / "docker",
        """#!/usr/bin/env bash
set -euo pipefail

commit='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
case "$1" in
  ps)
    printf '%s\\n' 'container-123'
    ;;
  image)
    if [[ "$*" == *'org.opencontainers.image.revision'* ]]; then
      printf '%s\\n' "$commit"
    else
      printf '%s\\n' 'sha256:expected-image'
    fi
    ;;
  inspect)
    if [[ "$*" == *'.State.Status'* ]]; then
      printf '%s\\n' 'running'
    elif [[ "$*" == *'.State.Health'* ]]; then
      printf '%s\\n' 'healthy'
    elif [[ "$*" == *'.Config.Env'* ]]; then
      cat <<'ENV'
AUTOBOT_OBSERVATION_ONLY_RUNTIME=true
PAPER_TRADING=false
PAPER_EXECUTION_ADAPTER_ENABLED=false
PAPER_EXECUTION_ROUTER_ENABLED=false
PAPER_TEST_TRADING_ENABLED=false
COLONY_AUTO_LIVE_PROMOTION=false
STRATEGY_ROUTER_LIVE_ENABLED=false
LIVE_TRADING_CONFIRMATION=false
ENV
    elif [[ "$*" == *'.Image'* ]]; then
      printf '%s\\n' 'sha256:expected-image'
    else
      exit 64
    fi
    ;;
  exec)
    printf '{\"program_execution_locked\":%s,\"observation_only_runtime\":%s,\"paper_execution_authorized\":%s,\"real_order_mutation_authorized\":%s}\\n' "${FAKE_PROGRAM_EXECUTION_LOCKED:?}" "${FAKE_OBSERVATION_ONLY_RUNTIME:?}" "${FAKE_PAPER_EXECUTION_AUTHORIZED:?}" "${FAKE_REAL_ORDER_MUTATION_AUTHORIZED:?}"
    ;;
  *)
    exit 64
    ;;
esac
""",
    )

    bash = shutil.which("bash")
    assert bash is not None, "deployment verifier requires Bash"
    shell_command = (
        f"PATH={shlex.quote(_bash_path(fake_bin))}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
        f"AUTOBOT_REPO_DIR={shlex.quote(_bash_path(repo))}; "
        f"FAKE_PROGRAM_EXECUTION_LOCKED={str(program_locked).lower()}; "
        f"FAKE_OBSERVATION_ONLY_RUNTIME={str(observation_only).lower()}; "
        f"FAKE_PAPER_EXECUTION_AUTHORIZED={str(paper_authorized).lower()}; "
        f"FAKE_REAL_ORDER_MUTATION_AUTHORIZED={str(real_order_authorized).lower()}; "
        f"FAKE_FINAL_HEALTH_PAYLOAD={shlex.quote(final_health_payload or '')}; "
        f"FAKE_HEALTH_CALL_FILE={shlex.quote(_bash_path(fake_bin / 'health-call'))}; "
        "export PATH AUTOBOT_REPO_DIR FAKE_PROGRAM_EXECUTION_LOCKED "
        "FAKE_OBSERVATION_ONLY_RUNTIME FAKE_PAPER_EXECUTION_AUTHORIZED "
        "FAKE_REAL_ORDER_MUTATION_AUTHORIZED FAKE_FINAL_HEALTH_PAYLOAD "
        "FAKE_HEALTH_CALL_FILE; "
        f"exec bash {shlex.quote(_bash_path(root / 'deploy' / 'verify-autobot-runtime-evidence.sh'))}"
    )
    environment = os.environ.copy()
    environment["FAKE_FINAL_HEALTH_PAYLOAD"] = final_health_payload or ""
    environment["FAKE_HEALTH_CALL_FILE"] = _bash_path(fake_bin / "health-call")
    return subprocess.run(
        [bash, "-c", shell_command],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
        timeout=_TEST_SUBPROCESS_TIMEOUT_SECONDS,
    )


def test_runtime_evidence_script_is_read_only_and_requires_strict_safety_proof():
    root = Path(__file__).resolve().parents[1]
    script = (root / "deploy" / "verify-autobot-runtime-evidence.sh").read_text(encoding="utf-8")

    assert "set -euo pipefail" in script
    assert "refs/remotes/origin/master" in script
    assert "Refusing deployment evidence" in script
    assert "docker compose" not in script
    assert "docker build" not in script
    assert "docker restart" not in script
    assert "docker stop" not in script
    assert "sendorder" not in script.lower()
    assert "KRAKEN_API_KEY" not in script
    assert "KRAKEN_API_SECRET" not in script
    assert "AUTOBOT_OBSERVATION_ONLY_RUNTIME=true" in script
    assert "PAPER_TRADING=false" in script
    assert "PAPER_EXECUTION_ADAPTER_ENABLED=false" in script
    assert "COLONY_AUTO_LIVE_PROMOTION=false" in script
    assert "STRATEGY_ROUTER_LIVE_ENABLED=false" in script
    assert "LIVE_TRADING_CONFIRMATION=false" in script
    assert 'docker exec --workdir /app/src "${CONTAINER_ID}" python -c' in script
    assert '"program_execution_locked": program_execution_locked()' in script
    assert '"paper_execution_authorized": paper_execution_authorized()' in script
    assert '"real_order_mutation_authorized": real_order_mutation_authorized()' in script
    assert "running container does not prove the program execution lock" in script
    assert "RuntimeDeploymentEvidence" in script
    assert '"container_healthy":true' in script
    assert '"program_execution_locked":true' in script
    assert '"paper_capital_disabled":true' in script
    assert '"live_disabled":true' in script
    assert "final health payload does not prove a connected WebSocket" in script
    assert "AUTOBOT container changed or is no longer healthy during verification" in script


@pytest.mark.integration
def test_runtime_evidence_verifier_accepts_only_the_exact_container_lock_state(tmp_path):
    valid = _run_verifier_with_fake_runtime_lock(tmp_path / "valid")
    forged_states = (
        _run_verifier_with_fake_runtime_lock(tmp_path / "program-unlocked", program_locked=False),
        _run_verifier_with_fake_runtime_lock(tmp_path / "observation-disabled", observation_only=False),
        _run_verifier_with_fake_runtime_lock(tmp_path / "paper-authorized", paper_authorized=True),
        _run_verifier_with_fake_runtime_lock(tmp_path / "real-order-authorized", real_order_authorized=True),
    )

    assert valid.returncode == 0, valid.stderr
    assert '"program_execution_locked":true' in valid.stdout
    for forged in forged_states:
        assert forged.returncode != 0
        assert "running container does not prove the program execution lock" in forged.stderr


@pytest.mark.integration
def test_runtime_evidence_verifier_rechecks_websocket_immediately_before_emitting_evidence(tmp_path):
    final_health_failure = _run_verifier_with_fake_runtime_lock(
        tmp_path / "final-health-failure",
        final_health_payload='{"status":"unhealthy","components":{"websocket":"disconnected"}}',
    )

    assert final_health_failure.returncode != 0
    assert "final health payload does not prove a connected WebSocket" in final_health_failure.stderr

from __future__ import annotations

from pathlib import Path
import shlex
import shutil
import subprocess

import pytest


pytestmark = pytest.mark.unit


def _bash_path(path: Path) -> str:
    """Return a path understood by native Bash or the Windows WSL shim."""

    resolved = path.resolve()
    if not resolved.drive:
        return str(resolved)
    return f"/mnt/{resolved.drive.rstrip(':').lower()}{resolved.as_posix()[2:]}"


def test_autobot_image_carries_an_explicit_source_revision_label():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ARG AUTOBOT_BUILD_COMMIT=unverified" in dockerfile
    assert "LABEL org.opencontainers.image.revision=${AUTOBOT_BUILD_COMMIT}" in dockerfile
    assert "ENV AUTOBOT_BUILD_COMMIT=${AUTOBOT_BUILD_COMMIT}" in dockerfile
    assert "AUTOBOT_BUILD_COMMIT: ${AUTOBOT_BUILD_COMMIT:-unverified}" in compose


def test_rebuild_helper_binds_image_label_to_clean_checkout_commit():
    root = Path(__file__).resolve().parents[1]
    script = (root / "deploy" / "rebuild-autobot-image.sh").read_text(encoding="utf-8")

    assert "BUILD_INPUT_PATHS=(" in script
    assert 'git -C "${REPO_DIR}" diff --quiet -- "${BUILD_INPUT_PATHS[@]}"' in script
    assert 'git -C "${REPO_DIR}" diff --cached --quiet -- "${BUILD_INPUT_PATHS[@]}"' in script
    assert 'git -C "${REPO_DIR}" ls-files --others --exclude-standard -- "${BUILD_INPUT_PATHS[@]}"' in script
    assert "reports/research" not in script
    assert 'MIN_FREE_DISK_BYTES="${AUTOBOT_DEPLOY_MIN_FREE_DISK_BYTES:-17179869184}"' in script
    assert 'df --output=avail -B1 "${REPO_DIR}"' in script
    assert "Refusing AUTOBOT build: available disk space" in script
    assert "docker builder prune" not in script
    assert "docker system prune" not in script
    assert 'SOURCE_COMMIT="$(git -C "${REPO_DIR}" rev-parse --verify HEAD)"' in script
    assert 'AUTOBOT_BUILD_COMMIT="${SOURCE_COMMIT}"' in script
    assert "'{{ index .Config.Labels \"org.opencontainers.image.revision\" }}'" in script
    assert '"${IMAGE_COMMIT}" != "${SOURCE_COMMIT}"' in script
    assert 'docker compose --project-directory "${REPO_DIR}" ps -q autobot' in script
    assert "AUTOBOT container was not created by the controlled rebuild." in script
    assert "'{{.State.Status}}'" in script
    assert "'{{.Image}}'" in script
    assert '"${CONTAINER_IMAGE_ID}" != "${EXPECTED_IMAGE_ID}"' in script


@pytest.mark.integration
def test_rebuild_helper_rejects_low_disk_before_git_or_docker(tmp_path):
    """The deployment preflight must fail before touching build inputs."""

    bash = shutil.which("bash")
    assert bash is not None, "deployment helper requires Bash"
    root = Path(__file__).resolve().parents[1]
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    invoked = tmp_path / "unexpected-tool-invocation"
    low_free_bytes = 16 * 1024**3 - 1

    (fake_bin / "df").write_text(
        "#!/usr/bin/env bash\nprintf 'Avail\\n%s\\n' '" + str(low_free_bytes) + "'\n",
        encoding="utf-8",
        newline="\n",
    )
    for command in ("git", "docker"):
        (fake_bin / command).write_text(
            "#!/usr/bin/env bash\ntouch '" + _bash_path(invoked).replace("'", "'\\''") + "'\nexit 99\n",
            encoding="utf-8",
            newline="\n",
        )
    for path in fake_bin.iterdir():
        path.chmod(0o755)

    shell_command = (
        f"PATH={shlex.quote(_bash_path(fake_bin))}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin; "
        f"AUTOBOT_REPO_DIR={shlex.quote(_bash_path(tmp_path / 'not-needed-before-preflight'))}; "
        f"AUTOBOT_DEPLOY_MIN_FREE_DISK_BYTES={16 * 1024**3}; "
        "export PATH AUTOBOT_REPO_DIR AUTOBOT_DEPLOY_MIN_FREE_DISK_BYTES; "
        f"exec bash {shlex.quote(_bash_path(root / 'deploy' / 'rebuild-autobot-image.sh'))}"
    )
    result = subprocess.run(
        [bash, "-c", shell_command],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )

    assert result.returncode != 0
    assert "available disk space" in result.stderr
    assert not invoked.exists()

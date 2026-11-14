"""Exercise the real deploy tar pipeline without SSH, LXD, or Docker.

A hard link models a file bind mount's reference to the original inode.
The API then reloads through that reference, rather than the host pathname.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ai_proxy.app import create_app
from ai_proxy.config.loader import load_config
from ai_proxy.core.routing import resolve_model

REPO_ROOT = Path(__file__).resolve().parents[3]


def _executable(path: Path, body: str) -> None:
    path.write_text(f"#!/bin/bash\nset -euo pipefail\n{body}\n")
    path.chmod(0o700)


@pytest.fixture
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    repo, staging, app, bin_dir = (tmp_path / name for name in ("repo", "staging", "app", "bin"))
    for path in (repo / "scripts", staging, app, bin_dir):
        path.mkdir(parents=True)
    shutil.copyfile(REPO_ROOT / "scripts/deploy.sh", repo / "scripts/deploy.sh")
    (repo / "deploy.env").write_text(
        f"DEPLOY_SSH_HOST=unused\nDEPLOY_LXD_CONTAINER=unused\n"
        f"DEPLOY_APP_DIR='{app}'\nDEPLOY_STAGING_DIR='{staging}'\nDEPLOY_HEALTH_URL=''\n"
    )
    # Execute only the local tar pipeline. Build/restart commands are no-ops.
    _executable(bin_dir / "ssh", r'shift; if [[ "$1" == tar\ * ]]; then bash -c "$1"; fi')
    _executable(bin_dir / "rsync", "exit 0")
    _executable(bin_dir / "sudo", 'exec "$@"')
    _executable(bin_dir / "lxc", 'shift 3; exec "$@"')
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return repo, staging, app


def _deploy(repo: Path) -> None:
    subprocess.run(  # noqa: S603 — runs the repository script with local command stubs
        ["bash", str(repo / "scripts/deploy.sh")],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    )


def _config(model: str) -> str:
    return f"providers:\n  test:\n    endpoint: https://example.com/v1\nmodel_mappings:\n  client: test:{model}\n"


async def test_reload_after_deploy_reads_new_routing(
    deployment: tuple[Path, Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, staging, app = deployment
    host_config = app / "config.yml"
    host_config.write_text(_config("old-model"))
    mounted_config = tmp_path / "mounted-config.yml"
    mounted_config.hardlink_to(host_config)
    original_inode = host_config.stat().st_ino
    secret = app / "config.secrets.yml"
    secret.write_text("api_keys: [test-secret]\n")
    load_config(str(mounted_config), secrets_path=str(secret))
    monkeypatch.setenv("CONFIG_PATH", str(mounted_config))
    monkeypatch.setenv("SECRETS_PATH", str(secret))
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        for model in ("new-model", "second-model-with-longer-name", "x"):
            (staging / "config.yml").write_text(_config(model))
            _deploy(repo)
            assert host_config.stat().st_ino == original_inode
            assert mounted_config.read_text() == _config(model)
            assert secret.read_text() == "api_keys: [test-secret]\n"
            response = await client.post("/admin/reload-config")
            assert response.status_code == 200
            assert response.json() == {"status": "reloaded"}
            route = await resolve_model("client")
            assert route.mapped_model == model


def test_deploy_installs_config_on_first_run(deployment: tuple[Path, Path, Path]) -> None:
    repo, staging, app = deployment
    (staging / "config.yml").write_text(_config("first-model"))
    _deploy(repo)
    assert (app / "config.yml").read_text() == _config("first-model")


@pytest.mark.skipif(
    os.environ.get("RUN_DOCKER_TESTS") != "1", reason="set RUN_DOCKER_TESTS=1 to test a real bind mount"
)
def test_deploy_updates_running_docker_file_mount(deployment: tuple[Path, Path, Path]) -> None:
    """Opt-in Linux Docker smoke test; Docker may pull the Alpine image."""
    repo, staging, app = deployment
    host_config = app / "config.yml"
    host_config.write_text(_config("old-model"))
    (staging / "config.yml").write_text(_config("new-model"))
    container = subprocess.check_output(  # noqa: S603
        [  # noqa: S607
            "docker",
            "run",
            "--rm",
            "-d",
            "--mount",
            f"type=bind,source={host_config},target=/config.yml,readonly",
            "alpine:3.21",
            "sleep",
            "120",
        ],
        text=True,
    ).strip()
    try:
        for expected in ("old-model", "new-model"):
            if expected == "new-model":
                _deploy(repo)
            content = subprocess.check_output(  # noqa: S603
                ["docker", "exec", container, "cat", "/config.yml"],  # noqa: S607
                text=True,
            )
            assert content == _config(expected)
    finally:
        subprocess.run(["docker", "rm", "-f", container], check=True, capture_output=True)  # noqa: S603, S607

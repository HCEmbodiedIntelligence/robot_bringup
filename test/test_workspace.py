"""Bootstrap integration tests use local Git repositories, never GitHub or hardware."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("workspace", ROOT / "scripts/workspace.py")
workspace = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workspace)


def command(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()


def commit(repo, text):
    (repo / "version.txt").write_text(text)
    command("git", "-C", repo, "add", "version.txt")
    command("git", "-C", repo, "commit", "-m", text)
    return command("git", "-C", repo, "rev-parse", "HEAD")


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "upstream with spaces"
    command("git", "init", "-b", "main", path)
    command("git", "-C", path, "config", "user.email", "test@example.invalid")
    command("git", "-C", path, "config", "user.name", "Test")
    commit(path, "initial")
    return path


def args(tmp_path):
    return SimpleNamespace(workspace=tmp_path / "working tree", transport="ssh")


def test_clone_then_fast_forward_and_preserve_local_changes(remote, tmp_path):
    options = args(tmp_path)
    entries = {"sample": {"type": "git", "url": str(remote), "version": "main"}}
    workspace.sync(options, entries)
    checkout = options.workspace / "src/sample"
    latest = commit(remote, "second")
    workspace.sync(options, entries)
    assert workspace.git(checkout, "rev-parse", "HEAD") == latest
    (checkout / "untracked.txt").write_text("keep me")
    commit(remote, "third")
    with pytest.raises(workspace.WorkspaceError, match="未提交"):
        workspace.sync(options, entries)
    assert workspace.git(checkout, "rev-parse", "HEAD") == latest
    assert (checkout / "untracked.txt").read_text() == "keep me"


def test_local_commits_are_not_overwritten(remote, tmp_path):
    options = args(tmp_path)
    entries = {"sample": {"type": "git", "url": str(remote), "version": "main"}}
    workspace.sync(options, entries)
    checkout = options.workspace / "src/sample"
    command("git", "-C", checkout, "config", "user.email", "test@example.invalid")
    command("git", "-C", checkout, "config", "user.name", "Test")
    local = commit(checkout, "local work")
    with pytest.raises(workspace.WorkspaceError, match="未推送"):
        workspace.sync(options, entries)
    assert workspace.git(checkout, "rev-parse", "HEAD") == local


def test_pinned_checkout_uses_exact_commit(remote, tmp_path):
    first = workspace.git(remote, "rev-parse", "HEAD")
    commit(remote, "newer")
    options = args(tmp_path)
    entries = {"sample": {"type": "git", "url": str(remote), "version": first}}
    workspace.sync(options, entries)
    checkout = options.workspace / "src/sample"
    assert workspace.git(checkout, "rev-parse", "HEAD") == first
    workspace.sync(options, entries)
    assert workspace.git(checkout, "rev-parse", "HEAD") == first


def test_wrong_origin_is_rejected_before_sync(remote, tmp_path):
    options = args(tmp_path)
    entries = {"sample": {"type": "git", "url": str(remote), "version": "main"}}
    workspace.sync(options, entries)
    entries["sample"]["url"] = str(tmp_path / "different")
    with pytest.raises(workspace.WorkspaceError, match="origin"):
        workspace.sync(options, entries)


def test_profiles_include_owned_gripper_package_and_actual_manager_remote(tmp_path):
    core = workspace.repositories(ROOT / "workspace.repos", "core")
    full = workspace.repositories(ROOT / "workspace.repos", "openarmx")
    assert "openarmx_driver" not in core
    assert "openarmx_driver" in full
    assert "humanoid_gripper" not in full  # Bundled, not a nonexistent GitHub repository.
    assert full["humanoid_manager"]["url"].endswith("/humanoid_adapter_manager.git")
    paths = workspace.package_paths(tmp_path, full)
    assert paths["humanoid_gripper"] == tmp_path / "src/robot_bringup/packages/humanoid_gripper"
    assert (ROOT / "packages/humanoid_gripper/package.xml").is_file()


def test_manifest_rejects_path_traversal(tmp_path):
    manifest = tmp_path / "bad.repos"
    manifest.write_text(json.dumps({"repositories": {"../outside": {"type": "git"}}}))
    with pytest.raises(workspace.WorkspaceError):
        workspace.repositories(manifest, "openarmx")


def test_existing_unversioned_gripper_is_not_overwritten(tmp_path):
    alias = tmp_path / "src/humanoid_gripper"
    alias.mkdir(parents=True)
    (alias / "local.txt").write_text("preserve")
    with pytest.raises(workspace.WorkspaceError, match="独立目录"):
        workspace.preflight_sync(tmp_path, {"openarmx_driver": {}})
    assert (alias / "local.txt").read_text() == "preserve"

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


def test_profiles_include_independent_gripper_only_for_adapter_development(tmp_path):
    core = workspace.repositories(ROOT / "workspace.repos", "core")
    full = workspace.repositories(ROOT / "workspace.repos", "openarmx")
    assert "openarmx_driver" not in core
    assert "openarmx_driver" in full
    assert "humanoid_gripper" not in core
    assert full["humanoid_gripper"]["url"].endswith("/humanoid_gripper.git")
    assert full["humanoid_manager"]["url"].endswith("/humanoid_adapter_manager.git")
    paths = workspace.package_paths(tmp_path, full)
    assert paths["humanoid_gripper"] == tmp_path / "src/humanoid_gripper"
    assert not (ROOT / "packages/humanoid_gripper/package.xml").exists()


def test_manifest_rejects_path_traversal(tmp_path):
    manifest = tmp_path / "bad.repos"
    manifest.write_text(json.dumps({"repositories": {"../outside": {"type": "git"}}}))
    with pytest.raises(workspace.WorkspaceError):
        workspace.repositories(manifest, "openarmx")


def test_existing_unversioned_gripper_is_not_overwritten(tmp_path):
    alias = tmp_path / "src/humanoid_gripper"
    alias.mkdir(parents=True)
    (alias / "local.txt").write_text("preserve")
    with pytest.raises(workspace.WorkspaceError, match="独立 Git 仓库"):
        workspace.preflight_sync(tmp_path, {"humanoid_gripper": {}})
    assert (alias / "local.txt").read_text() == "preserve"


@pytest.mark.parametrize('dangling', [False, True])
def test_legacy_link_migrates_to_independent_clone_without_deleting_target(remote, tmp_path, dangling):
    options = args(tmp_path)
    alias = options.workspace / 'src/humanoid_gripper'
    alias.parent.mkdir(parents=True)
    original = options.workspace / 'src/robot_bringup/packages/humanoid_gripper'
    if not dangling:
        original.mkdir(parents=True)
        (original / 'keep.txt').write_text('keep original')
    alias.symlink_to('robot_bringup/packages/humanoid_gripper', target_is_directory=True)
    entries = {'humanoid_gripper': {'type': 'git', 'url': str(remote), 'version': 'main'}}
    workspace.sync(options, entries)
    assert alias.is_dir() and not alias.is_symlink()
    assert (alias / '.git').is_dir()
    assert (alias / 'version.txt').read_text() == 'initial'
    if not dangling:
        assert (original / 'keep.txt').read_text() == 'keep original'
    workspace.sync(options, entries)


def test_failed_gripper_clone_preserves_legacy_link(tmp_path):
    options = args(tmp_path)
    alias = options.workspace / 'src/humanoid_gripper'
    alias.parent.mkdir(parents=True)
    alias.symlink_to('robot_bringup/packages/humanoid_gripper', target_is_directory=True)
    entries = {'humanoid_gripper': {'type': 'git', 'url': str(tmp_path / 'missing'), 'version': 'main'}}
    with pytest.raises(workspace.WorkspaceError):
        workspace.sync(options, entries)
    assert alias.is_symlink()


def test_unrelated_dangling_gripper_link_is_not_overwritten(tmp_path):
    alias = tmp_path / 'src/humanoid_gripper'
    alias.parent.mkdir(parents=True)
    alias.symlink_to(tmp_path / 'unrelated')
    with pytest.raises(workspace.WorkspaceError, match='独立 Git 仓库'):
        workspace.preflight_sync(tmp_path, {'humanoid_gripper': {}})
    assert alias.is_symlink()


def test_core_removes_only_obsolete_dangling_alias_without_cloning_gripper(tmp_path):
    options = args(tmp_path)
    alias = options.workspace / 'src/humanoid_gripper'
    alias.parent.mkdir(parents=True)
    alias.symlink_to('robot_bringup/packages/humanoid_gripper', target_is_directory=True)
    workspace.sync(options, {})
    assert not alias.is_symlink()
    assert not alias.exists()


def test_default_setup_only_builds_generic_platform_without_zip_or_robot_selection(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(workspace, "require_platform", lambda: None)
    for operation in ("sync", "build", "bundle"):
        monkeypatch.setattr(workspace, operation,
                            lambda args, entries, operation=operation: calls.append((operation, set(entries))))
    assert workspace.main(["setup", "--workspace", str(tmp_path)]) == 0
    assert [name for name, _ in calls] == ["sync", "build"]
    for _, entries in calls:
        assert len(entries) == 8
        assert not entries & {"openarmx_driver", "openarmx_description", "humanoid_gripper"}
    assert not (tmp_path / "deploy_artifacts").exists()
    assert not (tmp_path / "core").exists()


def test_arbitrary_profiles_are_selected_from_manifest_data(tmp_path):
    entries = {name: {'type': 'git', 'url': 'https://example.invalid/' + name, 'version': 'main'}
               for name in ('platform', 'brand_new_arm', 'vacuum_tool')}
    manifest = tmp_path / 'workspace.repos'
    manifest.write_text(json.dumps({'repositories': entries, 'profiles': {
        'bench': {'repositories': ['platform', 'vacuum_tool']}}}))
    assert list(workspace.repositories(manifest, 'bench')) == ['platform', 'vacuum_tool']
    with pytest.raises(workspace.WorkspaceError, match='profile'):
        workspace.repositories(manifest, 'undefined')

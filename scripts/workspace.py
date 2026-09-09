#!/usr/bin/env python3
"""Fetch, build and package the managed ROS 2 workspace. Bootstrap needs only Git and Python."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


REPOSITORY = Path(__file__).resolve().parents[1]
OPENARMX = {"openarmx_driver", "openarmx_description", "humanoid_gripper"}
ROS_SETUP = Path("/opt/ros/humble/setup.bash")


class WorkspaceError(RuntimeError):
    pass


def run(argv, *, cwd=None, capture=False, env=None):
    argv = [str(value) for value in argv]
    if not capture:
        print("+ " + shlex.join(argv), flush=True)
    result = subprocess.run(argv, cwd=cwd, env=env, text=True,
                            stdout=subprocess.PIPE if capture else None,
                            stderr=subprocess.PIPE if capture else None)
    if result.returncode:
        raise WorkspaceError(f"命令失败 ({result.returncode}): {shlex.join(argv)}\n"
                             + ((result.stderr or result.stdout or "") if capture else ""))
    return result.stdout.strip() if capture else ""


def git(path, *arguments):
    return run(["git", "-C", path, *arguments], capture=True)


def repositories(manifest, profile):
    # JSON is a YAML subset; the same manifest also works with vcstool.
    entries = json.loads(Path(manifest).read_text())["repositories"]
    result = {}
    for name, item in entries.items():
        if not re.fullmatch(r"[A-Za-z0-9_]+", name) or item.get("type") != "git":
            raise WorkspaceError(f"不支持的仓库条目: {name}")
        if not isinstance(item.get("url"), str) or not item["url"] or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_./-]*", item.get("version", "")):
            raise WorkspaceError(f"无效的 URL 或版本: {name}")
        if profile == "openarmx" or name not in OPENARMX:
            result[name] = item
    return result


def canonical_remote(url):
    return url.removesuffix(".git").replace("git@github.com:", "https://github.com/").rstrip("/")


def legacy_gripper_link(workspace):
    alias = workspace / "src/humanoid_gripper"
    bundled = workspace / "src/robot_bringup/packages/humanoid_gripper"
    return alias.is_symlink() and alias.resolve() == bundled.resolve()


def preflight_sync(workspace, entries):
    for name, item in entries.items():
        path = workspace / "src" / name
        if name == "humanoid_gripper" and legacy_gripper_link(workspace):
            continue  # Replaced only after the independent clone succeeds.
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not (path / ".git").exists():
            raise WorkspaceError(f"目标已存在且不是独立 Git 仓库: {path}")
        if git(path, "status", "--porcelain"):
            raise WorkspaceError(f"{name} 有未提交修改；请先提交或自行保存。同步未开始。")
        if canonical_remote(git(path, "remote", "get-url", "origin")) != canonical_remote(item["url"]):
            raise WorkspaceError(f"{name} 的 origin 与仓库清单不符，未修改该目录。")
        branch = git(path, "branch", "--show-current")
        if not re.fullmatch(r"[a-f0-9]{40}", item["version"]) and branch != item["version"]:
            raise WorkspaceError(f"{name} 当前分支为 {branch or 'detached HEAD'}，要求 {item['version']}。")


def sync_one(path, item, transport):
    network_env = dict(os.environ)
    network_env.setdefault("GIT_SSH_COMMAND", "ssh -o ConnectTimeout=15 -o ServerAliveInterval=10 -o ServerAliveCountMax=3")
    url = item["url"]
    if transport == "https":
        url = canonical_remote(url) + ".git" if "github.com" in url else url
    ref = item["version"]
    pinned = bool(re.fullmatch(r"[a-f0-9]{40}", ref))
    old = git(path, "rev-parse", "HEAD") if path.exists() else None
    if old is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone"]
        if not pinned:
            command += ["--branch", ref, "--single-branch"]
        run([*command, "--", url, path], env=network_env)
        if not pinned:
            return True
    run(["git", "-C", path, "fetch", "--no-tags", "origin", ref], env=network_env)
    target = git(path, "rev-parse", "FETCH_HEAD")
    if pinned:
        if target != ref:
            raise WorkspaceError(f"{path.name}: 下载版本与锁定提交不符")
        if git(path, "rev-parse", "HEAD") != target:
            if old is not None and subprocess.run([
                    "git", "-C", str(path), "merge-base", "--is-ancestor", "HEAD", target]).returncode:
                raise WorkspaceError(f"{path.name}: 当前提交不在锁定版本的历史中；请先自行保存或切换。")
            run(["git", "-C", path, "checkout", "--detach", target])
    elif git(path, "rev-parse", "HEAD") != target:
        ancestor = subprocess.run(["git", "-C", str(path), "merge-base", "--is-ancestor", "HEAD", target])
        if ancestor.returncode:
            raise WorkspaceError(f"{path.name} 有未推送提交或分支分叉；需要先处理，未覆盖本地提交。")
        run(["git", "-C", path, "merge", "--ff-only", target])
    return old != git(path, "rev-parse", "HEAD")


def sync(args, entries):
    preflight_sync(args.workspace, entries)
    # Update the entry repository first, then re-read any new manifest/script.
    names = sorted(entries, key=lambda name: name != "robot_bringup")
    for name in names:
        path = args.workspace / "src" / name
        if name == "humanoid_gripper" and legacy_gripper_link(args.workspace):
            # Clone first. A failed download must not remove the old link.
            with tempfile.TemporaryDirectory(prefix=".gripper-migration-", dir=path.parent) as temporary:
                checkout = Path(temporary) / "checkout"
                sync_one(checkout, entries[name], args.transport)
                if not legacy_gripper_link(args.workspace):
                    raise WorkspaceError("夹爪路径在同步期间发生变化，未替换该目录。")
                original = path.readlink()
                path.unlink()  # Only the verified legacy symlink, never its target.
                try:
                    checkout.rename(path)
                except OSError:
                    path.symlink_to(original, target_is_directory=True)
                    raise
            print("humanoid_gripper 已从旧软链接迁移为独立仓库；原链接目标未删除。")
            changed = True
        else:
            changed = sync_one(path, entries[name], args.transport)
        if changed and name == "robot_bringup" and path.resolve() == REPOSITORY:
            print("统一入口已更新，重新载入仓库清单。", flush=True)
            os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
    if "humanoid_gripper" not in entries and legacy_gripper_link(args.workspace):
        alias = args.workspace / "src/humanoid_gripper"
        if not alias.exists():
            alias.unlink()
            print("已移除旧夹爪悬空软链接；通用安装不拉取夹爪插件源码。")
    print(f"已同步 {len(entries)} 个仓库。")


def package_paths(workspace, entries):
    return {name: workspace / "src" / name for name in entries}


def require_sources(workspace, entries):
    missing = [name for name, path in package_paths(workspace, entries).items()
               if not (path / "package.xml").is_file()]
    if missing:
        raise WorkspaceError("源码不完整，请先 sync：" + ", ".join(missing))


def require_platform():
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        raise WorkspaceError("当前运动 SDK 仅支持 Intel/AMD x86-64，不能在 ARM/Jetson 上构建运行。")
    if not ROS_SETUP.is_file():
        raise WorkspaceError("请先安装 Ubuntu 22.04 的 ROS 2 Humble：缺少 /opt/ros/humble/setup.bash")
    release = platform.freedesktop_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "22.04":
        raise WorkspaceError("当前 SDK 要求 Ubuntu 22.04；检测到 " + release.get("PRETTY_NAME", "未知系统"))


def ros_command(workspace, command, *, overlay=True, env=None, capture=False):
    setup = workspace / "install/setup.bash" if overlay else ROS_SETUP
    if not setup.is_file():
        raise WorkspaceError(f"缺少 {setup}，请先 build。")
    process_env = dict(os.environ if env is None else env)
    # Do not let a previously sourced workspace supply stale build dependencies.
    for key in ("AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH", "CMAKE_PREFIX_PATH", "PYTHONPATH", "LD_LIBRARY_PATH"):
        process_env.pop(key, None)
    return run(["bash", "-c", 'source "$1" || exit; shift; exec "$@"', "bash", setup, *command],
               cwd=workspace, env=process_env, capture=capture)


def install_dependencies(args, entries):
    require_platform()
    require_sources(args.workspace, entries)
    if not shutil.which("rosdep"):
        raise WorkspaceError("请先 sudo apt install python3-rosdep python3-colcon-common-extensions")
    if not Path("/etc/ros/rosdep/sources.list.d/20-default.list").is_file():
        run(["sudo", "rosdep", "init"])
    run(["rosdep", "update", "--rosdistro", "humble"])
    ros_command(args.workspace, ["rosdep", "install", "--from-paths",
                *package_paths(args.workspace, entries).values(),
                "--ignore-src", "--rosdistro", "humble", "-y"], overlay=False)
    command = [args.workspace / "src/humanoid_motion_server/scripts/install_sdk_dependencies_ubuntu2204.sh",
               "--jobs", str(args.jobs)]
    if args.sdk_source:
        command += ["--source-root", args.sdk_source]
    run(command, cwd=args.workspace)
    run([args.workspace / "src/humanoid_manager/setup_web.sh"], cwd=args.workspace)


def build(args, entries):
    require_platform()
    require_sources(args.workspace, entries)
    print("检查运动 SDK 的完整性和系统动态库依赖。", flush=True)
    checked = ros_command(args.workspace, [args.workspace / "src/humanoid_motion_server/scripts/check_sdk_runtime",
                "--sdk-root", args.workspace / "src/humanoid_motion_server/vendor/robo_manip"], overlay=False, capture=True)
    print(checked.splitlines()[-1], flush=True)
    env = dict(os.environ, CMAKE_BUILD_PARALLEL_LEVEL=str(args.jobs), MAKEFLAGS=f"-j{args.jobs}")
    paths = package_paths(args.workspace, entries)
    ros_command(args.workspace, ["colcon", "build", "--base-paths",
                *paths.values(),
                "--packages-select", *paths, "--symlink-install", "--cmake-clean-cache",
                "--executor", "sequential"], overlay=False, env=env)


def bundle(args, entries):
    if args.profile != "openarmx":
        raise WorkspaceError("core 只安装通用软件；OpenArmX 整机打包请选择 --profile openarmx。")
    # Deliberately always build before packaging: no reuse of old deployment ZIPs.
    build(args, entries)
    output = args.output or args.workspace / "deploy_artifacts" / (
        "openarmx-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    ros_command(args.workspace, ["/usr/bin/python3", args.workspace / "src/robot_bringup/scripts/create_release.py",
                "--workspace", args.workspace, "--output", output,
                "--manifest", args.manifest, "--robot-id", args.robot_id])


def status(args, entries):
    for name in entries:
        path = args.workspace / "src" / name
        if not (path / ".git").exists():
            print(f"{name:28} 未拉取")
            continue
        dirty = bool(git(path, "status", "--porcelain"))
        print(f"{name:28} {git(path, 'rev-parse', '--short=12', 'HEAD')}"
              f" {'有本地修改' if dirty else '干净'}")


def web(args, _entries):
    command = [args.workspace / "src/humanoid_manager/start_configurator.sh",
               "--host", args.host, "--port", str(args.port), "--domain-id", str(args.domain_id)]
    for key in ("plugin_root", "state_root"):
        if getattr(args, key):
            command += ["--" + key.replace("_", "-"), getattr(args, key)]
    run(command, cwd=args.workspace)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("sync", "status", "deps", "build", "bundle", "setup", "web"))
    default_workspace = REPOSITORY.parent.parent if REPOSITORY.parent.name == "src" else Path.cwd()
    parser.add_argument("--workspace", type=Path, default=default_workspace)
    parser.add_argument("--profile", choices=("core", "openarmx"), default="core",
                        help="默认只安装通用平台；openarmx 供适配器开发使用")
    parser.add_argument("--manifest", type=Path, default=REPOSITORY / "workspace.repos")
    parser.add_argument("--transport", choices=("ssh", "https"), default="ssh")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--output", type=Path, help="整机产物目录（必须不存在）")
    parser.add_argument("--robot-id", default="openarmx_v10_bimanual")
    parser.add_argument("--install-deps", action="store_true", help="setup 时安装 ROS/SDK/网页依赖，可能需要 sudo")
    parser.add_argument("--sdk-source", type=Path, help="已有 alg_dep 源码目录，供 deps 使用")
    parser.add_argument("--host", default="0.0.0.0", help="web 的监听地址")
    parser.add_argument("--port", type=int, default=7876)
    parser.add_argument("--domain-id", type=int, default=14)
    parser.add_argument("--plugin-root", type=Path)
    parser.add_argument("--state-root", type=Path)
    args = parser.parse_args(argv)
    args.workspace = args.workspace.expanduser().resolve()
    args.manifest = args.manifest.expanduser().resolve()
    if args.output:
        args.output = args.output.expanduser().resolve()
    if args.sdk_source:
        args.sdk_source = args.sdk_source.expanduser().resolve()
    if args.jobs < 1:
        parser.error("--jobs 必须为正整数")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.robot_id):
        parser.error("无效的 --robot-id")
    try:
        entries = repositories(args.manifest, args.profile)
        if args.command == "setup":
            require_platform()
            sync(args, entries)
            if args.install_deps:
                install_dependencies(args, entries)
            build(args, entries)
            print("通用软件已就绪。下一步运行 ./src/robot_bringup/workspace.sh web，在网页中配置机器人。")
        else:
            {"sync": sync, "status": status, "deps": install_dependencies,
             "build": build, "bundle": bundle, "web": web}[args.command](args, entries)
    except (WorkspaceError, OSError, ValueError, KeyError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Internal packaging step, invoked by workspace.sh bundle after a successful build."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from humanoid_manager.configuration import ConfigurationManager
from humanoid_manager.deployment import deploy_archive, validate_archive, resolve_robot_deployment

from workspace import repositories, git, package_paths


def digest(path):
    checksum = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def source_versions(workspace, entries):
    result = {}
    for name in entries:
        path = workspace / "src" / name
        result[name] = {"commit": git(path, "rev-parse", "HEAD"),
                        "dirty": bool(git(path, "status", "--porcelain"))}
    return result


def build_release(workspace, output, manifest, robot_id):
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError(f"产物目录已存在，请另选 --output：{output}")
    entries = repositories(manifest, "openarmx")
    paths = package_paths(workspace, entries)
    versions = source_versions(workspace, entries)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".openarmx-release-", dir=output.parent) as temporary:
        work = Path(temporary)
        release = work / "release"
        release.mkdir()
        specifications = [
            ("driver", "openarmx_driver", "tools/create_deployment_bundle.py", [
                workspace / "install/openarmx_driver", release / "driver.zip"]),
            ("model", "openarmx_driver", "tools/create_model_bundle.py", [
                release / "model.zip", "--description-share",
                workspace / "src/openarmx_description"]),
            ("gripper", "humanoid_gripper", "tools/create_deployment_bundle.py", [
                workspace / "install/humanoid_gripper", release / "gripper.zip",
                "--config", "openarmx_v10_bimanual.yaml",
                "--plugin-id", "openarmx_v10_bimanual_gripper"]),
        ]
        manifests = {}
        for kind, package, script, arguments in specifications:
            subprocess.run(["/usr/bin/python3", str(paths[package] / script),
                            *map(str, arguments)], check=True)
            archive = release / f"{kind}.zip"
            manifests[kind] = validate_archive(archive, check_linkage=True)
            deploy_archive(archive, work / "plugins")

        # Check the installed libraries, not the differently linked build-tree ELF files.
        for kind, package in (("driver", "openarmx_driver"), ("gripper", "humanoid_gripper")):
            member = manifests[kind]["library"]
            with zipfile.ZipFile(release / f"{kind}.zip") as archive:
                packed_hash = hashlib.sha256(archive.read(member)).hexdigest()
            installed = workspace / "install" / package / "lib" / Path(member).name
            if digest(installed) != packed_hash:
                raise ValueError(f"{kind}: ZIP 与本次安装的驱动库不一致")

        manager = ConfigurationManager(work / "plugins", work / "state")
        robot = manager.create(robot_id, "OpenArmX v10 双臂", driver_id=manifests["driver"]["plugin_id"],
                               model_id=manifests["model"]["plugin_id"],
                               gripper_id=manifests["gripper"]["plugin_id"])
        complete = release / "openarmx-v10-complete.zip"
        manager.export(robot_id, robot["latest"], complete)

        # Exercise exactly the manager-page import and apply path using temporary state.
        imported_manager = ConfigurationManager(work / "import-plugins", work / "import-state")
        imported = imported_manager.import_workspace(complete, "release_acceptance", "导入验收")
        imported_manager.apply(imported["robot_id"], imported["latest"], imported["etag"])
        resolved = resolve_robot_deployment(work / "import-plugins", imported["robot_id"])
        if not resolved.gripper_class or "hc_teleop_config" not in resolved.resources:
            raise ValueError("整机包导入后缺少夹爪或遥操作配置")

        controller_config = paths["humanoid_gripper"] / "config/v10_controllers/openarmx_v10_split_controllers.yaml"
        shutil.copyfile(controller_config, release / controller_config.name)
        if any(item["dirty"] for item in versions.values()):
            print("提示：本次含本地未提交修改，已在 source-revisions.json 中标记。")
        lock = {"repositories": {name: {**entry, "version": versions[name]["commit"]}
                                  for name, entry in entries.items()}}
        (release / "workspace.lock.repos").write_text(json.dumps(lock, indent=2) + "\n")
        report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                  "architecture": "x86_64", "ros_distro": "humble", "robot_id": robot_id,
                  "repositories": versions, "manager_import_apply_verified": True,
                  "hardware_verified": False,
                  "sha256": {path.name: digest(path) for path in sorted(release.iterdir())}}
        (release / "source-revisions.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        (release / "README.txt").write_text(
            "在 humanoid_manager 的机器人配置页面，选择“导入配置包”，类型为整机配置。\n"
            "上传 openarmx-v10-complete.zip，填写新的配置 ID 和名称，导入后保存并应用。\n"
            "不要解压整机 ZIP；driver.zip/model.zip/gripper.zip 仅供单独导入插件。\n"
            "夹爪映射已提供，默认关闭；可在夹爪配置中启用。机械臂前端默认也未使能。\n"
            "官方硬件层须使用每臂 7 轴、夹爪独立的控制器；配置见同目录 YAML。\n"
            "目标机要求 Ubuntu 22.04 x86-64、ROS 2 Humble 和运动 SDK 的系统依赖。\n"
            "本包已验证管理器导入及解析，尚未验收真实硬件运动。\n", encoding="utf-8")
        release.rename(output)
    print(f"整机配置包：{output / 'openarmx-v10-complete.zip'}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--robot-id", default="openarmx_v10_bimanual")
    args = parser.parse_args()
    build_release(args.workspace, args.output, args.manifest, args.robot_id)


if __name__ == "__main__":
    main()

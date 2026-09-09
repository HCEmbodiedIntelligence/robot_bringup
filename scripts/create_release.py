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
from humanoid_manager.plugin_metadata import expand
from humanoid_manager.deployment import deploy_archive, validate_archive, resolve_robot_deployment

from workspace import repositories, git


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


def build_release(workspace, output, manifest, robot_id="", *, recipe, profile="core"):
    recipe = json.loads(Path(recipe).read_text())
    if recipe.get("schema_version") != 1:
        raise ValueError("unsupported release recipe schema")
    robot_id = robot_id or recipe["robot_id"]
    artifact_name = recipe.get("artifact_name", robot_id + "-complete.zip")
    if Path(artifact_name).name != artifact_name or not artifact_name.endswith(".zip"):
        raise ValueError("artifact_name must be a ZIP filename")
    workspace, output = Path(workspace).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError(f"产物目录已存在，请另选 --output：{output}")
    entries = repositories(manifest, profile)
    versions = source_versions(workspace, entries)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".robot-release-", dir=output.parent) as temporary:
        work = Path(temporary)
        release = work / "release"
        release.mkdir()
        manifests = {}
        for index, specification in enumerate(recipe['plugins']):
            role = specification['role']
            if role not in {'driver', 'model', 'gripper'}:
                raise ValueError('plugin role must be driver, model or gripper')
            key = role if role != 'gripper' else 'gripper-' + str(index)
            if key in manifests:
                raise ValueError(f'duplicate plugin role: {role}')
            archive = release / f'{key}.zip'
            values = {'workspace': str(workspace), 'output': str(archive)}
            command = expand(specification['command'], values)
            if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
                raise ValueError('release command must be an argv list')
            subprocess.run(command, check=True, cwd=workspace)
            checked = validate_archive(archive, check_linkage=True)
            expected = {'driver': 'hardware_driver', 'model': 'robot_model', 'gripper': 'gripper_driver'}[role]
            if checked.get('plugin_type') != expected:
                raise ValueError(f'{key}: recipe role differs from produced plugin type')
            manifests[key] = checked
            deploy_archive(archive, work / 'plugins')
            if 'installed_library' in specification:
                installed = Path(expand(specification['installed_library'], values))
                with zipfile.ZipFile(archive) as packed:
                    checksum = hashlib.sha256(packed.read(checked['library'])).hexdigest()
                if digest(installed) != checksum:
                    raise ValueError(f'{key}: ZIP differs from the installed library')

        manager = ConfigurationManager(work / "plugins", work / "state")
        grippers = [value for key, value in manifests.items() if key.startswith('gripper-')]
        robot = manager.create(robot_id, recipe['name'], driver_id=manifests['driver']['plugin_id'],
                               model_id=manifests['model']['plugin_id'],
                               gripper_id=grippers[0]['plugin_id'] if len(grippers) == 1 else '',
                               gripper_ids={f'gripper_{i}': item['plugin_id'] for i, item in enumerate(grippers)} if len(grippers) > 1 else None)
        complete = release / artifact_name
        manager.export(robot_id, robot['latest'], complete)

        # Exercise exactly the manager-page import and apply path using temporary state.
        imported_manager = ConfigurationManager(work / "import-plugins", work / "import-state")
        imported = imported_manager.import_workspace(complete, "release_acceptance", "导入验收")
        imported_manager.apply(imported["robot_id"], imported["latest"], imported["etag"])
        resolved = resolve_robot_deployment(work / "import-plugins", imported["robot_id"])
        if len(resolved.gripper_instances) != len(grippers):
            raise ValueError('imported gripper instance count differs from recipe')
        for relative in recipe.get('files', []):
            source = workspace / relative
            shutil.copyfile(source, release / source.name)
        if any(item["dirty"] for item in versions.values()):
            print("提示：本次含本地未提交修改，已在 source-revisions.json 中标记。")
        lock = {"profiles": {profile: {"repositories": list(entries)}}, "repositories": {name: {**entry, "version": versions[name]["commit"]}
                                  for name, entry in entries.items()}}
        (release / "workspace.lock.repos").write_text(json.dumps(lock, indent=2) + "\n")
        report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                  "architecture": "x86_64", "ros_distro": "humble", "robot_id": robot_id,
                  "repositories": versions, "manager_import_apply_verified": True,
                  "hardware_verified": False,
                  "sha256": {path.name: digest(path) for path in sorted(release.iterdir())}}
        (release / "source-revisions.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        (release / 'README.txt').write_text(
            f"在机器人配置页面导入 {artifact_name}，保存、应用并启动机器人。\n"
            + recipe.get('notes', '') + "\n已验证管理器导入、应用与解析；尚未验收真实硬件运动。\n",
            encoding='utf-8')
        release.rename(output)
    print(f"整机配置包：{output / artifact_name}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--robot-id", default="")
    parser.add_argument("--profile", default="core")
    parser.add_argument("--recipe", type=Path, required=True)
    args = parser.parse_args()
    build_release(args.workspace, args.output, args.manifest, args.robot_id, recipe=args.recipe, profile=args.profile)


if __name__ == "__main__":
    main()

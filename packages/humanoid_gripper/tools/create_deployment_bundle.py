#!/usr/bin/env python3
"""Package one installed humanoid_gripper configuration for manager deployment."""

from __future__ import annotations

import argparse
from pathlib import Path
import platform
import shutil
import tempfile

import yaml

from humanoid_manager.deployment import DeploymentError, pack_directory


PACKAGE = "humanoid_gripper"
PLUGIN_CLASS = "humanoid_gripper/RosTopicGripperDriver"
LIBRARY_NAME = "libhumanoid_ros_topic_gripper_driver.so"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installed_prefix", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--config",
        default="ros_topic_gripper.yaml",
        help="Configuration filename installed below share/humanoid_gripper/config.",
    )
    parser.add_argument("--plugin-id", default="humanoid_gripper_ros_topic")
    parser.add_argument("--name", default="ROS topic gripper adapter")
    return parser.parse_args()


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise DeploymentError(f"installed humanoid_gripper file is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main() -> int:
    args = arguments()
    installed = args.installed_prefix.resolve()
    config_relative = Path(args.config)
    if config_relative.name != args.config or config_relative.suffix not in {".yaml", ".yml"}:
        raise DeploymentError("--config must be one YAML filename")

    with tempfile.TemporaryDirectory(prefix="humanoid_gripper_bundle_") as temporary:
        root = Path(temporary) / "bundle"
        prefix = root / "prefix"
        installed_share = installed / "share" / PACKAGE
        for relative in (
            "package.xml",
            "plugins/gripper_plugins.xml",
            f"config/{args.config}",
        ):
            copy_file(installed_share / relative, prefix / "share" / PACKAGE / relative)
        copy_file(
            installed / "share/ament_index/resource_index/packages" / PACKAGE,
            prefix / "share/ament_index/resource_index/packages" / PACKAGE,
        )
        copy_file(
            installed / "lib" / LIBRARY_NAME,
            prefix / "lib" / LIBRARY_NAME,
        )

        architecture = platform.machine().lower()
        architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(
            architecture, architecture
        )
        manifest = {
            "schema_version": 1,
            "artifact_type": "plugin",
            "plugin_type": "gripper_driver",
            "plugin_id": args.plugin_id,
            "name": args.name,
            "compatibility": {
                "ros_distro": "humble",
                "architecture": architecture,
                "driver_interface_abi": 1,
            },
            "package_name": PACKAGE,
            "ament_prefix": "prefix",
            "plugin_xml": f"prefix/share/{PACKAGE}/plugins/gripper_plugins.xml",
            "library": f"prefix/lib/{LIBRARY_NAME}",
            "plugin_class": PLUGIN_CLASS,
            "resources": {
                "gripper_params": f"prefix/share/{PACKAGE}/config/{args.config}",
            },
        }
        root.mkdir(parents=True, exist_ok=True)
        (root / "manifest.yaml").write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )
        pack_directory(root, args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

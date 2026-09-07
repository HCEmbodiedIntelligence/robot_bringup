#!/usr/bin/env python3
"""Compatibility entry point for the manager-owned robot launch."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from humanoid_manager.deployment import DEFAULT_PLUGIN_ROOT


def generate_launch_description():
    managed_launch = Path(get_package_share_directory("humanoid_manager")) / "launch" / "managed_robot.launch.py"
    arguments = {
        name: LaunchConfiguration(name)
        for name in ("robot_id", "plugin_root", "start_driver", "start_gripper", "start_motion", "start_teleop", "start_cameras")
    }
    return LaunchDescription(
        [
            DeclareLaunchArgument("robot_id", description="Robot ID configured and applied by humanoid_manager."),
            DeclareLaunchArgument("plugin_root", default_value=str(DEFAULT_PLUGIN_ROOT)),
            DeclareLaunchArgument("start_driver", default_value="true"),
            DeclareLaunchArgument("start_gripper", default_value="true"),
            DeclareLaunchArgument("start_motion", default_value="true"),
            DeclareLaunchArgument("start_teleop", default_value="false"),
            DeclareLaunchArgument("start_cameras", default_value="true"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(managed_launch)),
                launch_arguments=arguments.items(),
            ),
        ]
    )

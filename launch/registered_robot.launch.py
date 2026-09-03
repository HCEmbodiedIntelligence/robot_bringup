#!/usr/bin/env python3
"""Launch the core stack from a robot composition managed by the adapter manager."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from humanoid_adapter_manager.deployment import (
    DEFAULT_PLUGIN_ROOT,
    resolve_robot_deployment,
)


def _launch_registered_robot(context):
    robot_id = LaunchConfiguration("robot_id").perform(context)
    if not robot_id:
        raise RuntimeError("robot_id is required")

    plugin_root = Path(LaunchConfiguration("plugin_root").perform(context)).resolve()
    deployment = resolve_robot_deployment(plugin_root, robot_id)
    resources = deployment.resources
    driver_environment = deployment.environment()
    resource_environment = deployment.resource_environment()
    start_driver = LaunchConfiguration("start_driver")
    start_motion = LaunchConfiguration("start_motion")
    start_teleop = LaunchConfiguration("start_teleop")

    actions = [
        Node(
            package="humanoid_driver_runtime",
            executable="humanoid_driver_runtime_node",
            name="humanoid_driver_runtime",
            output="screen",
            parameters=[
                str(resources["driver_params"]),
                {
                    "plugin_class": deployment.driver_class,
                    "plugin_xml_paths": [
                        str(path) for path in deployment.driver_plugin_xml_paths
                    ],
                },
            ],
            additional_env=driver_environment,
            condition=IfCondition(start_driver),
            on_exit=Shutdown(reason="humanoid driver runtime exited"),
        ),
        Node(
            package="humanoid_motion_server",
            executable="humanoid_motion_control_node",
            name="humanoid_motion_control",
            output="screen",
            parameters=[
                str(resources["motion_params"]),
                {
                    "channel_config_file": str(resources["channel_config"]),
                    "sdk_config_file": str(resources["sdk_config"]),
                    "tool_config_file": str(resources["tool_config"]),
                    "urdf_file": str(resources["urdf"]),
                },
            ],
            additional_env=resource_environment,
            condition=IfCondition(start_motion),
            on_exit=Shutdown(reason="humanoid motion server exited"),
        ),
    ]

    if "teleop_config" in resources:
        actions.append(
            Node(
                package="teleop_vr_recv",
                executable="teleop_vr_recv_node",
                name="teleop_vr_recv",
                output="screen",
                parameters=[{"config_file": str(resources["teleop_config"])}],
                additional_env=resource_environment,
                condition=IfCondition(start_teleop),
                on_exit=Shutdown(reason="teleoperation frontend exited"),
            )
        )
    elif LaunchConfiguration("start_teleop").perform(context).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise RuntimeError(
            "start_teleop is true but the deployed profile has no teleop_config"
        )

    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "robot_id",
                description="Deployed robot-composition ID below plugin_root.",
            ),
            DeclareLaunchArgument(
                "plugin_root",
                default_value=str(DEFAULT_PLUGIN_ROOT),
                description="Adapter-manager deployment root.",
            ),
            DeclareLaunchArgument("start_driver", default_value="true"),
            DeclareLaunchArgument("start_motion", default_value="true"),
            DeclareLaunchArgument("start_teleop", default_value="false"),
            OpaqueFunction(function=_launch_registered_robot),
        ]
    )

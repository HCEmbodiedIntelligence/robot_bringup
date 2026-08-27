#!/usr/bin/env python3
"""Start the complete OpenArmX bimanual MuJoCo teleoperation stack."""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, Shutdown, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _enabled(context, name: str) -> bool:
    return LaunchConfiguration(name).perform(context).strip().lower() in {
        "1", "true", "yes", "on"
    }


def _launch_stack(context):
    bringup_share = Path(get_package_share_directory("robot_bringup"))
    description_share = Path(get_package_share_directory("openarmx_description"))
    mujoco_share = Path(get_package_share_directory("openarmx_mujoco"))
    profile = (
        bringup_share
        / "config"
        / "humanoid_stack"
        / "openarmx_v10_bimanual"
    )

    required = {
        "driver": profile / "driver.yaml",
        "motion": profile / "motion_control.yaml",
        "channels": profile / "channels.yaml",
        "sdk": profile / "sdk.yaml",
        "tools": profile / "tools.yaml",
        "teleop": profile / "teleop_vr_recv.toml",
        "urdf": description_share / "urdf" / "robot" / "openarmx_robot.urdf",
        "mujoco": mujoco_share / "openarmx_control_scene.xml",
    }
    missing = [f"{name}={path}" for name, path in required.items() if not path.is_file()]
    if missing:
        raise RuntimeError("missing OpenArmX runtime resources: " + ", ".join(missing))

    actions = []
    if _enabled(context, "start_simulator"):
        simulator_arguments = ["--model", str(required["mujoco"])]
        if _enabled(context, "headless"):
            simulator_arguments.append("--headless")
        actions.append(
            Node(
                package="openarmx_mujoco",
                executable="openarmx_mujoco_bridge",
                output="screen",
                arguments=simulator_arguments,
                on_exit=Shutdown(reason="OpenArmX MuJoCo exited"),
            )
        )

    if _enabled(context, "start_driver"):
        actions.append(
            Node(
                package="humanoid_driver_runtime",
                executable="humanoid_driver_runtime_node",
                name="humanoid_driver_runtime",
                output="screen",
                parameters=[str(required["driver"])],
                on_exit=Shutdown(reason="humanoid driver runtime exited"),
            )
        )

    if _enabled(context, "start_motion"):
        actions.append(
            Node(
                package="humanoid_motion_server",
                executable="humanoid_motion_control_node",
                name="humanoid_motion_control",
                output="screen",
                parameters=[
                    str(required["motion"]),
                    {
                        "channel_config_file": str(required["channels"]),
                        "sdk_config_file": str(required["sdk"]),
                        "tool_config_file": str(required["tools"]),
                        "urdf_file": str(required["urdf"]),
                    },
                ],
                on_exit=Shutdown(reason="humanoid motion server exited"),
            )
        )

    start_teleop = _enabled(context, "start_teleop")
    if start_teleop:
        actions.append(
            Node(
                package="teleop_vr_recv",
                executable="teleop_vr_recv_node",
                name="teleop_vr_recv",
                output="screen",
                parameters=[{"config_file": str(required["teleop"])}],
                on_exit=Shutdown(reason="VR teleoperation frontend exited"),
            )
        )

    if start_teleop and _enabled(context, "auto_enable_teleop"):
        actions.append(
            TimerAction(
                period=1.0,
                actions=[
                    Node(
                        package="robot_bringup",
                        executable="enable_teleop_channels.py",
                        name="openarmx_teleop_channel_enabler",
                        output="screen",
                    )
                ],
            )
        )

    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "headless",
                default_value="false",
                description="Run MuJoCo without its graphical viewer.",
            ),
            DeclareLaunchArgument("start_simulator", default_value="true"),
            DeclareLaunchArgument("start_driver", default_value="true"),
            DeclareLaunchArgument("start_motion", default_value="true"),
            DeclareLaunchArgument("start_teleop", default_value="true"),
            DeclareLaunchArgument(
                "auto_enable_teleop",
                default_value="true",
                description="Enable both VR channels after startup.",
            ),
            OpaqueFunction(function=_launch_stack),
        ]
    )

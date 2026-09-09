#!/usr/bin/env python3
"""Single public entry point: web UI and independently restartable robot services.

External hardware launches must belong to the robot child process, not beside
the web process; otherwise the web stop/restart buttons cannot supervise them.
Configure EXTERNAL_BRINGUP once for the machine, or supply vendor_* arguments.
Use web:=false only for legacy headless integrations.
"""

import json
from pathlib import Path

from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription, OpaqueFunction, Shutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from humanoid_manager.deployment import DEFAULT_PLUGIN_ROOT


# Integrators may fill their tested vendor launch here. Empty means the plugin
# connects hardware directly, or vendor services are independently supervised.
# For OpenArmX, select its installed bringup package and tested launch file.
# Supply your tested arguments, including the split 7-joint arm/gripper
# controllers; do not enable the vendor's default 8-joint arm controllers.
EXTERNAL_BRINGUP = {'package': '', 'launch_file': '', 'arguments': {}}


def workspace_root():
    for candidate in (Path(__file__).resolve(), Path(get_package_prefix('robot_bringup'))):
        for parent in (candidate, *candidate.parents):
            if (parent / 'src/humanoid_manager/start_configurator.sh').is_file():
                return str(parent)
    return ''  # Binary-only headless installations do not need the web script.


def launch_system(context):
    value = lambda name: LaunchConfiguration(name).perform(context)
    bringup = json.dumps({'package': value('vendor_package'), 'launch_file': value('vendor_launch_file'),
                          'arguments': json.loads(value('vendor_arguments'))})
    if value('web').lower() not in {'true', '1', 'yes', 'on'}:
        if not value('robot_id'):
            raise RuntimeError('仅机器人模式需要显式 robot_id')
        arguments = {name: value(name) or default for name, default in (
            ('robot_id', ''), ('plugin_root', str(DEFAULT_PLUGIN_ROOT)),
            ('start_driver', 'true'), ('start_gripper', 'true'), ('start_motion', 'true'),
            ('start_teleop', 'false'), ('start_cameras', 'true'))}
        arguments['bringup_json'] = bringup
        managed_launch = Path(get_package_share_directory('humanoid_manager')) / 'launch/managed_robot.launch.py'
        return [IncludeLaunchDescription(PythonLaunchDescriptionSource(str(managed_launch)),
                                         launch_arguments=arguments.items())]
    for name in ('start_driver', 'start_gripper', 'start_motion'):
        if value(name).lower() not in {'true', '1', 'yes', 'on'}:
            raise RuntimeError(f'统一网页模式需要 {name}:=true；组件调试请使用 web:=false')
    script = Path(value('workspace')) / 'src/humanoid_manager/start_configurator.sh'
    if not value('workspace') or not script.is_file():
        raise RuntimeError('找不到 humanoid_manager/start_configurator.sh，请传 workspace:=源码工作区路径')
    command = [str(script),
               '--run-robot', '--bringup-json', bringup]
    for name in ('host', 'port', 'domain_id', 'plugin_root', 'state_root', 'robot_id',
                 'start_teleop', 'start_cameras'):
        if value(name):
            command += ['--' + name.replace('_', '-'), value(name)]
    return [ExecuteProcess(cmd=command, output='screen', sigterm_timeout='20', sigkill_timeout='5',
                           on_exit=Shutdown(reason='机器人网页管理进程退出'))]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('web', default_value='true'),
        DeclareLaunchArgument('workspace', default_value=workspace_root()),
        # Empty values preserve the selection and settings saved through the UI.
        *[DeclareLaunchArgument(name, default_value='') for name in (
            'robot_id', 'plugin_root', 'host', 'port', 'domain_id', 'state_root',
            'start_teleop', 'start_cameras')],
        *[DeclareLaunchArgument(name, default_value='true') for name in (
            'start_driver', 'start_gripper', 'start_motion')],
        DeclareLaunchArgument('vendor_package', default_value=EXTERNAL_BRINGUP['package']),
        DeclareLaunchArgument('vendor_launch_file', default_value=EXTERNAL_BRINGUP['launch_file']),
        DeclareLaunchArgument('vendor_arguments', default_value=json.dumps(EXTERNAL_BRINGUP['arguments'])),
        OpaqueFunction(function=launch_system),
    ])

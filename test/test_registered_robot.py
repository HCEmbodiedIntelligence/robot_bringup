"""The original launch is the only public entry; robot processes stay isolated."""
import importlib.util
import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import sys

import pytest
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.utilities import perform_substitutions


@pytest.fixture
def entry(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "launch/registered_robot.launch.py"
    spec = importlib.util.spec_from_file_location("registered_robot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_package_share_directory", lambda package: str(tmp_path / package))

    return module


def context_for(entry, **values):
    context = LaunchContext()
    for action in entry.generate_launch_description().entities:
        if isinstance(action, DeclareLaunchArgument):
            action.execute(context)
    context.launch_configurations.update(values)
    return context


def test_default_starts_web_supervisor_not_hardware(entry):
    context = context_for(entry)
    actions = entry.launch_system(context)
    assert len(actions) == 1 and isinstance(actions[0], ExecuteProcess)
    command = [perform_substitutions(context, part) for part in actions[0].cmd]
    assert command[0].endswith('/humanoid_manager/start_configurator.sh')
    assert '--run-robot' in command
    assert '--robot-id' not in command
    assert '--start-teleop' not in command


def test_headless_compatibility_delegates_every_component(entry):
    actions = entry.launch_system(context_for(entry, web='false', robot_id='my_robot', start_teleop='true'))
    assert len(actions) == 1 and isinstance(actions[0], IncludeLaunchDescription)
    arguments = dict(actions[0].launch_arguments)
    assert set(arguments) == {'robot_id', 'plugin_root', 'start_driver', 'start_gripper',
                              'start_motion', 'start_teleop', 'start_cameras', 'bringup_json'}
    assert arguments['robot_id'] == 'my_robot'
    assert arguments['start_teleop'] == 'true'


def test_vendor_is_forwarded_to_owned_child_not_started_beside_web(entry):
    context = context_for(entry, robot_id='my_robot', vendor_package='vendor_bringup',
                          vendor_launch_file='robot.launch.py', vendor_arguments='{"use_mock":"true"}')
    actions = entry.launch_system(context)
    assert len(actions) == 1 and isinstance(actions[0], ExecuteProcess)
    command = [perform_substitutions(context, part) for part in actions[0].cmd]
    assert json.loads(command[command.index('--bringup-json') + 1]) == {
        'package': 'vendor_bringup', 'launch_file': 'robot.launch.py', 'arguments': {'use_mock': 'true'}}


def test_headless_requires_robot_id(entry):
    with pytest.raises(RuntimeError, match='robot_id'):
        entry.launch_system(context_for(entry, web='false'))


def test_original_launch_really_serves_web_and_exits_cleanly(tmp_path):
    aiohttp = pytest.importorskip('aiohttp')
    pytest.importorskip('mcap')
    from humanoid_manager.web.config import ConfigStore
    source = Path(__file__).resolve().parents[1]
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    state = tmp_path / 'state'
    store = ConfigStore(state / 'configurator.yaml')
    # No ROS observer and no configured robot: this smoke test cannot start hardware.
    store.save({'server': {'host': '127.0.0.1', 'port': port}, 'ros': {'enabled': False},
        'adapter_manager': {'enabled': True, 'plugin_root': str(tmp_path / 'plugins'),
            'state_root': str(state / 'configuration'),
            'cli': str(source.parent / 'humanoid_manager/scripts/humanoid_pluginctl.py')}})
    async def check():
        with (tmp_path / 'launch.log').open('w') as log:
            process = await asyncio.create_subprocess_exec('ros2', 'launch',
                str(source / 'launch/registered_robot.launch.py'), f'state_root:={state}',
                stdout=log, stderr=log, start_new_session=True,
                env={**os.environ, 'HUMANOID_WEB_PYTHON': sys.executable,
                     'ROS_LOG_DIR': str(tmp_path / 'ros_logs')})
            try:
                async with aiohttp.ClientSession() as client:
                    for _ in range(150):
                        try:
                            async with client.get(f'http://127.0.0.1:{port}/api/launcher') as response:
                                document = await response.json()
                                assert document['runtime']['enabled'] is True
                                assert document['runtime']['owned_processes'] == 0
                                assert document['selected_robot'] == ''
                                break
                        except aiohttp.ClientConnectionError:
                            if process.returncode is not None:
                                raise AssertionError((tmp_path / 'launch.log').read_text())
                            await asyncio.sleep(.1)
                    else:
                        raise AssertionError((tmp_path / 'launch.log').read_text())
                    async with client.get(f'http://127.0.0.1:{port}/dashboard/') as response:
                        assert response.status == 200
                        assert '开启机器人' in await response.text()
            finally:
                if process.returncode is None:
                    process.send_signal(signal.SIGINT)
                    try:
                        await asyncio.wait_for(process.wait(), 25)
                    except asyncio.TimeoutError:
                        os.killpg(process.pid, signal.SIGKILL)
                        await process.wait()
                        raise
            assert process.returncode == 0, (tmp_path / 'launch.log').read_text()
    asyncio.run(check())

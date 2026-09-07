"""Verify frontend selection without starting any robot process."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from launch import LaunchContext
import pytest


def test_registered_robot_selects_hc_frontend(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "launch/registered_robot.launch.py"
    spec = importlib.util.spec_from_file_location("registered_robot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resources = {key: tmp_path / key for key in
                 ("driver_params", "motion_params", "channel_config", "sdk_config", "tool_config", "urdf", "hc_teleop_config")}
    deployment = SimpleNamespace(resources=resources, driver_class="test/Driver", driver_plugin_xml_paths=[],
                                 environment=lambda: {}, resource_environment=lambda: {})
    monkeypatch.setattr(module, "resolve_robot_deployment", lambda root, ident: deployment)
    # Isolate frontend selection from the configurator's independent run-state reporter.
    if hasattr(module, "acquire_deployment_lock"):
        monkeypatch.setattr(module, "acquire_deployment_lock", lambda *args, **kwargs: None)
        monkeypatch.setattr(module, "configuration_identity", lambda *args: {"robot_id": "arbitrary_robot"})
    context = LaunchContext()
    context.launch_configurations.update(robot_id="arbitrary_robot", plugin_root=str(tmp_path),
                                         start_driver="false", start_motion="false", start_teleop="true")
    actions = module._launch_registered_robot(context)
    frontends = [a for a in actions if a.node_package == "hc_teleop_recv"]
    assert len(frontends) == 1
    assert frontends[0].node_package == "hc_teleop_recv"
    assert frontends[0].node_executable == "hc_teleop_recv_node"

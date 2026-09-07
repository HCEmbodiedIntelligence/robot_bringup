"""Verify the compatibility launch delegates every component to the manager."""
import importlib.util
from pathlib import Path

from launch.actions import IncludeLaunchDescription


def test_registered_robot_delegates_to_managed_launch(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "launch/registered_robot.launch.py"
    spec = importlib.util.spec_from_file_location("registered_robot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "get_package_share_directory", lambda package: str(tmp_path / package))

    actions = module.generate_launch_description().entities
    includes = [action for action in actions if isinstance(action, IncludeLaunchDescription)]
    assert len(includes) == 1
    assert set(dict(includes[0].launch_arguments)) == {
        "robot_id", "plugin_root", "start_driver", "start_motion", "start_teleop", "start_cameras"
    }

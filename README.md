# robot_bringup

`robot_bringup` is the robot-independent orchestration layer. It resolves a robot composition
deployment managed by `humanoid_manager`, then starts the selected driver runtime,
motion server, and optional teleoperation frontend.

Start a managed deployment:

```bash
ros2 launch robot_bringup registered_robot.launch.py robot_id:=my_robot
```

Concrete robot resources and vendor launch logic do not belong in this package. The target only
receives validated plugin artifacts; it does not install robot-specific source packages. See
[`docs/registering_robot.md`](docs/registering_robot.md) for the deployment contract.

With `start_teleop:=true`, a model's `hc_teleop_config` starts `hc_teleop_recv` using the
configuration resolved by the manager. The HC frontend outputs ServoP poses and obtains measured
FK from the motion server. The retired `teleop_vr_recv` frontend is not part of this launch path.

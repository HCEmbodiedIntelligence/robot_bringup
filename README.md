# robot_bringup

`robot_bringup` is the robot-independent orchestration layer. It resolves a robot composition
deployment managed by `humanoid_adapter_manager`, then starts the selected driver runtime,
motion server, and optional teleoperation frontend.

Start a managed deployment:

```bash
ros2 launch robot_bringup registered_robot.launch.py robot_id:=my_robot
```

Concrete robot resources and vendor launch logic do not belong in this package. The target only
receives validated plugin artifacts; it does not install robot-specific source packages. See
[`docs/registering_robot.md`](docs/registering_robot.md) for the deployment contract.

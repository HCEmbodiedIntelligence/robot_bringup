# robot_bringup

统一下载和构建入口见 [一键部署说明](docs/workspace.md)。首次克隆本仓库到
`teleop_ws/src/robot_bringup` 后，在工作区执行：

```bash
./src/robot_bringup/workspace.sh setup --install-deps --jobs 2
```

默认拉取 OpenArmX 所需仓库，构建后生成管理器页面可直接导入的
`openarmx-v10-complete.zip`。仅拉源码用 `workspace.sh sync`；仅通用软件用 `--profile core`。

`robot_bringup` is a compatibility entry point for robot-independent orchestration. It delegates
to `humanoid_manager/managed_robot.launch.py`, which starts the selected driver runtime, motion
server, optional gripper runtime, teleoperation frontend, configured cameras, and configuration-state reporter.

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

`start_cameras:=true` is the default and starts the camera list saved on the robot page. Use
`start_cameras:=false` only when camera drivers are supervised separately.

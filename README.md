# robot_bringup

统一下载和构建入口见 [通用平台安装说明](docs/workspace.md)。首次克隆本仓库到
`teleop_ws/src/robot_bringup` 后，在工作区执行：

```bash
./src/robot_bringup/workspace.sh setup --install-deps --jobs 2
```

默认仅拉取并构建 8 个通用软件仓库，不下载或生成整机 ZIP，不预选机器人。
随后运行 `./src/robot_bringup/workspace.sh web`，在网页中导入驱动/模型、新建并配置机器人。
仅拉源码用 `workspace.sh sync`。`core` 是默认安装选项的名字，不会生成 core 文件夹。

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

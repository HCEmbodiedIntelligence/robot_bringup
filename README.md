# robot_bringup

Robot-specific deployment profiles and complete launch files live here. Robot geometry remains
in `openarmx_description`; generic motion and driver code remain in their platform packages.

OpenArmX 官方 `ros2_control` Topic、HC 驱动插件边界、真机启动流程和上机验收项见
[`docs/openarmx_v10_real_hardware.md`](docs/openarmx_v10_real_hardware.md)。当前 profile 仍是
MuJoCo 配置；完成文档中的专用插件和真机 profile 前，不可直接用于实体机器人。

## OpenArmX v10 bimanual simulation

Build and launch the complete MuJoCo, driver, motion-server and PICO VR stack:

```bash
cd /home/czy/teleop_ws
colcon build --packages-up-to robot_bringup
source install/setup.bash
ros2 launch robot_bringup openarmx_v10_bimanual.launch.py
```

For a machine without a display:

```bash
ros2 launch robot_bringup openarmx_v10_bimanual.launch.py headless:=true
```

Disable the VR frontend when testing Move actions directly:

```bash
ros2 launch robot_bringup openarmx_v10_bimanual.launch.py \
  headless:=true start_teleop:=false auto_enable_teleop:=false
```

The profile exposes these actions:

- `/motion/left_arm/move_j`, `/motion/right_arm/move_j`
- `/motion/left_arm/move_l`, `/motion/right_arm/move_l`
- `/motion/left_arm/move_p`, `/motion/right_arm/move_p`

Continuous Cartesian teleoperation remains on `/teleop/<arm>/servo_p`, with measured FK on
`/teleop/<arm>/fk_pose`.

With the headless test launch running, the separately packaged motion tools can exercise the
real action path against MuJoCo feedback:

```bash
ros2 run humanoid_motion_tools verify_motion_actions.py
```

This verifier checks all six left/right action servers, moves the left seventh joint by only
0.05 rad through `MoveJ`, then calls `MoveL` and `MoveP` using the current measured FK pose.
It is a manual test tool and is never started by the bringup launch.

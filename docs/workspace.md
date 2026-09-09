# 通用平台安装与网页配置

`robot_bringup` 是统一入口。默认仅拉取、构建以下 8 个通用仓库：

- `humanoid_manager`：网页配置、运行状态和数据管理。
- `hc_teleop_recv`：遥操作输入接收与映射。
- `humanoid_motion_server`：运动计算和控制接口。
- `humanoid_driver_runtime`、`humanoid_driver_interface`：驱动加载、运行时及接口。
- `humanoid_motion_interfaces`：ROS 消息与 Action 定义。
- `humanoid_camera`：通用相机接入。
- `robot_bringup`：启动已配置的机器人及统一拉取脚本。

安装不会生成 `core` 文件夹，不会下载或生成整机 ZIP，也不会导入、选中或启动某款机器人。
机型、驱动、模型、关节及遥操作参数由用户在管理器网页中配置。

## 新机器安装

目标电脑要求 **Ubuntu 22.04、Intel/AMD x86-64、ROS 2 Humble**。需要 GitHub 私有仓库
访问权限；预先安装 `git`、`python3-rosdep` 和 `python3-colcon-common-extensions`。

```bash
mkdir -p teleop_ws/src
git clone git@github.com:HCEmbodiedIntelligence/robot_bringup.git teleop_ws/src/robot_bringup
cd teleop_ws
./src/robot_bringup/workspace.sh setup --install-deps --jobs 2
source install/setup.bash
ros2 launch robot_bringup registered_robot.launch.py
```

setup 会拉取源码、安装 ROS/SDK/网页依赖并构建。SDK 的系统依赖源码编译可能耗时较长，
安装时可能请求 sudo 密码。已有 `alg_dep` 可加 `--sdk-source /path/to/alg_dep`；
系统依赖已安装的电脑可省略 `--install-deps`。

统一 launch 提供网页和机器人开启/关闭/重启按钮，地址 `http://机器人IP:7876/dashboard/#robots`，
首次默认 ROS Domain 为 14，已有设置保持不变。也可指定地址、端口和配置存放目录：

```bash
ros2 launch robot_bringup registered_robot.launch.py host:=0.0.0.0 port:=7876 domain_id:=14
```

需要自定义目录时追加 `plugin_root:=/path/to/plugins state_root:=/path/to/manager-state`。
默认插件目录优先使用已有 `/var/lib/humanoid-plugins`，否则使用 `~/.local/share/humanoid-plugins`。
原 `workspace.sh web` 保留为只开网页、不监管机器人的兼容入口。网页仅应部署在可信局域网。

## 在网页配置机器人

首次运行时没有预设机器人，按以下流程操作：

1. 在网页分别导入对应的机械臂驱动插件和模型插件，按需导入夹爪插件。
2. 点击“新建机器人”，填写 ID 和名称，选择已导入的驱动及模型。
3. 在页面编辑驱动话题、关节映射、URDF、运动通道、遥操作输入和坐标映射；按需配置相机与夹爪。
4. 点击“保存配置”。系统校验关节、限位、坐标系、话题和资源的一致性，生成配置版本。
5. 点击“开启机器人”；以后修改并保存后，提示“重启机器人后生效”，由用户点击“重启机器人”。

这里的驱动/模型插件是分别导入的适配资源，不要求提供整机 ZIP。驱动插件必须实现平台接口；
只填写厂商名称或 IP 不能代替缺失的硬件驱动。
网页保存不会启动运动，也不会热改正在运行的机器人。“开启/重启”在机器人停止后自动应用最新保存版本。
管理器必须取得新鲜 ROS 节点状态确认机器人已停止；“关闭/重启”只处理本入口管理的机器人和厂商服务，不会关闭网页。
关闭浏览器不影响服务；Ctrl+C 退出统一 launch 则关闭整套服务。首次未选择机器人时只开网页；以后同一命令启动上次开启的机器人。

不需要每次按机器人 ID 换命令。原有仅机器人脚本仍保留给外部进程监管的高级集成（不能再同时点击网页开启）：

```bash
ROS_DOMAIN_ID=14 ./src/robot_bringup/scripts/start_robot.sh 你在网页填写的机器人ID
```

如果网页使用自定义插件目录，启动命令追加 `plugin_root:=/同一个目录`。
硬件层和管理器使用相同 ROS Domain。底层 CAN、厂商 SDK 或 ros2_control 的启动由对应硬件
适配完成；本入口按网页配置启动平台运行时、运动服务、接收端和已配置相机。
厂商自有 launch 可在 `registered_robot.launch.py` 的 `EXTERNAL_BRINGUP` 中配置，随按钮统一监管，
具体见 [统一启动说明](../README.md)。不要同时在别处再次启动同一组驱动。

## 更新

```bash
./src/robot_bringup/workspace.sh sync
./src/robot_bringup/workspace.sh build --jobs 2
```

同步会先检查未提交修改及 origin，仅允许快进更新，不会自动 stash、reset 或覆盖本地提交。
`workspace.sh status` 显示当前版本。仓库清单位于 `workspace.repos`；
`humanoid_manager` 的现有远端仍叫 `humanoid_adapter_manager`，清单已处理目录名映射。

`--profile core` 是默认选项，表示上述通用软件。`--profile openarmx` 仅供开发适配器时显式选择，
会额外拉取 `openarmx_driver`、`openarmx_description` 和独立的 `humanoid_gripper` 仓库；
夹爪源码位于 `src/humanoid_gripper`，不再放在 `robot_bringup/packages` 中。机器人正常安装无需此选项。
旧的 `src/humanoid_gripper` 若是指向内置包的软链接，OpenArmX 同步会先克隆成功再替换链接；
其他已有目录、错误链接、未提交修改或不同 origin 都不会被覆盖。
迁移后使用 `workspace.sh build --profile openarmx` 清理 CMake 缓存并重建；
手工构建夹爪包时追加 `--cmake-clean-cache`，避免缓存仍指向旧目录。
旧的 `HC-teleop-robotic`、`teleop_vr_recv` 和 MuJoCo 不参与默认链路。

配置流程的软件验收使用独立 ROS Domain 和 Mock 驱动；真实机器人仍需核对关节方向、零位，
并完成低速动作及停止验证。

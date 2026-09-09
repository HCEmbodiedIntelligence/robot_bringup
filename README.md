# robot_bringup

统一下载和构建入口见 [通用平台安装说明](docs/workspace.md)。首次克隆本仓库到
`teleop_ws/src/robot_bringup` 后，在工作区执行：

```bash
./src/robot_bringup/workspace.sh setup --install-deps --jobs 2
```

默认仅拉取并构建 8 个通用软件仓库，不下载或生成整机 ZIP，不预选机器人。
随后运行下面的统一 launch，在网页中导入驱动/模型、新建并配置机器人。
仅拉源码用 `workspace.sh sync`。`core` 是默认安装选项的名字，不会生成 core 文件夹。

`humanoid_gripper` 已拆为独立插件仓库，源码路径为 `src/humanoid_gripper`。
本仓库不再携带夹爪实现。默认通用安装不拉取夹爪源码；机器人只需通过网页导入预编译的夹爪 ZIP。
开发 OpenArmX 适配器时，`--profile openarmx` 才会关联拉取和编译这个独立仓库。

## 一个入口启动网页和机器人服务

原有 `registered_robot.launch.py` 现为统一入口，不需要另一套 launch 或每次手写机器人 ID：

```bash
source install/setup.bash
ros2 launch robot_bringup registered_robot.launch.py
```

访问 `http://机器人IP:7876/dashboard/#robots`。已有网页设置（目录、端口、ROS 域）继续沿用。
首次安装未选机器人时只运行网页；在页面选择配置，保存后点击“开启机器人”。
此后重新运行同一命令会加载上次明确开启的机器人及遥操作/相机选项。

- “保存配置”只校验和生成新版本，提示“重启机器人后生效”，不会自动启动或重启。
- “开启机器人 / 重启机器人”加载所选机器人的最新保存版本。
- “关闭机器人 / 重启机器人”只操作此入口启动的机器人及厂商服务，网页和配置保留。
- 关闭浏览器不影响服务；终端 Ctrl+C 则关闭本入口的网页和机器人。进程意外退出不会自动反复启动。
- “进程已启动”不代表硬件连接成功，请查看运行状态、驱动诊断和启动日志。“关闭机器人”不是硬件急停。

第一次迁移时请先退出旧网页与旧机器人启动进程。自定义目录可以一次指定：

```bash
ros2 launch robot_bringup registered_robot.launch.py \
  plugin_root:=/absolute/path/to/plugins host:=0.0.0.0
```

已有 `state_root` 绑定的插件目录必须一致，避免读到另一套配置。首次启动默认监听所有网卡；
已有配置若只监听 localhost，可用 `host:=0.0.0.0` 更新。网页仅应放在可信机器人局域网，不要暴露到公网。

## 接入 OpenArmX 等厂商 launch

在 [registered_robot.launch.py](launch/registered_robot.launch.py) 顶部的 `EXTERNAL_BRINGUP`
中填写已安装、验证过的 ROS 包、launch 文件名及参数，例如：

```python
EXTERNAL_BRINGUP = {
    'package': 'your_vendor_bringup',
    'launch_file': 'robot.launch.py',
    'arguments': {'your_argument': 'your_value'},
}
```

修改后重新构建 `robot_bringup`。也支持 `vendor_package:=... vendor_launch_file:=... vendor_arguments:='{"key":"value"}'`。
参数值须为字符串；不接受 `$(...)` 表达式。厂商 launch 应直接管理自己的子进程，不应自行 daemonize 或启动脱离监管的服务。
这些服务在机器人子进程内启动，随网页按钮一起关闭/重启；不能作为网页的平级独立进程，否则按钮无法管理它们。
厂商包需事先安装并编译，不会自动下载；默认不启动任何特定厂商硬件。
OpenArmX 应填写实际验证过的启动参数，确保机械臂 7 轴控制器与夹爪分离，不可直接套用默认 8 轴机械臂控制器。

内部 `humanoid_manager/managed_robot.launch.py` 保留为隔离的子进程实现，用户无需单独运行。
旧的仅机器人集成可显式指定 `web:=false robot_id:=my_robot`，然后使用原组件开关。
默认遥操作关闭，相机开启；网页可选择。遥操作使用模型的 `hc_teleop_config` 启动 `hc_teleop_recv`，不启动旧接收端。
插件部署协议见 [docs/registering_robot.md](docs/registering_robot.md)。

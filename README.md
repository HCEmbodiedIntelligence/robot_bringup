# robot_bringup

机器人通用平台的源码同步、安装构建和统一启动入口。机器人型号、驱动、模型及参数通过网页配置，
不需要下载或生成整机 ZIP。详细环境要求见 [通用平台安装说明](docs/workspace.md)。

## 一键入口与代码位置

- [workspace.sh](workspace.sh)：一键命令入口。
- [scripts/workspace.py](scripts/workspace.py)：仓库检查、拉取、更新和构建逻辑。
- [workspace.repos](workspace.repos)：仓库地址与版本清单。
- [launch/registered_robot.launch.py](launch/registered_robot.launch.py)：启动网页并管理机器人服务。

各项目下载到工作区的 `src/项目名称`，例如 `src/humanoid_manager`。
默认 `core` 选项仅拉取并构建 8 个通用软件仓库，不预选机器人，也不会生成 `core` 文件夹。
`humanoid_gripper` 是独立的可选插件仓库，不包含在默认安装中，见后面的夹爪源码说明。

以下以机器人上的 `~/workspace/teleop_ws` 为例；使用其他路径时替换为实际工作区。

## 全新机器安装

要求 Ubuntu 22.04、Intel/AMD x86-64、已安装 ROS 2 Humble，以及清单中 GitHub 仓库的访问权限。
需预先安装 `git`、`python3-rosdep` 和 `python3-colcon-common-extensions`。
已有 `src/robot_bringup` 时不要再次克隆到同名目录，使用下一节的更新流程。

```bash
mkdir -p ~/workspace/teleop_ws/src
cd ~/workspace/teleop_ws
git clone git@github.com:HCEmbodiedIntelligence/robot_bringup.git src/robot_bringup

./src/robot_bringup/workspace.sh setup --install-deps --jobs 2

# 安装和编译成功后启动
source install/setup.bash
ros2 launch robot_bringup registered_robot.launch.py
```

`setup --install-deps` 会同步源码、安装 ROS/运动 SDK/网页依赖并编译，可能请求 sudo 密码。
它不导入插件、不生成整机 ZIP、不启动机器人；机器人由后面的 launch 和网页按钮控制。
完整环境已安装时可以省略 `--install-deps`。

## 已有部分代码，或更新后继续使用

先在旧启动终端按 `Ctrl+C`，退出旧网页与机器人服务。已有环境不必重复安装。
对于之前使用普通 `colcon build` 的工作区，执行：

```bash
cd ~/workspace/teleop_ws

# 补齐缺失的通用仓库，并更新已有仓库
./src/robot_bringup/workspace.sh sync

# 保持原有普通构建方式，清除旧 CMake 源码路径缓存
source /opt/ros/humble/setup.bash
colcon build --cmake-clean-cache

# 仅在同步和编译都成功后执行
source install/setup.bash
ros2 launch robot_bringup registered_robot.launch.py
```

如果同步或编译报错，先处理错误，不要继续启动旧的安装产物。
若原工作区一直使用 `--symlink-install`，编译时也保留该参数。
本脚本的 `setup/build` 使用 symlink-install；由本脚本安装的工作区可用
`./src/robot_bringup/workspace.sh build --jobs 2` 替代上面的普通 `colcon build`。
不要直接混用普通构建和 symlink-install：仅清 CMake 缓存不能解决两种模式遗留的 Python 目录/软链接冲突。

直接运行 `colcon build` 会构建工作区中可发现的所有包；`workspace.sh build` 只构建所选仓库清单中的包。
如果本次只想补齐、更新源码，运行 `sync` 即可；它不安装环境、不编译，也不启动服务。

### 再次拉取会不会覆盖已有代码？

会更新仓库中受版本管理的源码，但不会强行覆盖本地修改：

| 当前状态 | 同步行为 |
| --- | --- |
| 仓库尚未下载 | 克隆到对应的 `src/项目名称` |
| 已有仓库，工作区干净 | 按清单快进更新或检出指定固定版本；已是目标版本则不改 |
| 有未提交修改或未跟踪文件 | 报错停止，保留文件，不自动 stash |
| 有本地提交，无法快进到清单版本 | 报错停止，不 reset、不覆盖提交 |
| 同名目录不是 Git 仓库，或 origin/分支不符合清单 | 报错，要求先处理，不覆盖目录 |
| 不在本次所选清单中的其他项目 | 不更新、不删除 |

同步前会检查已有仓库。同步不是整批回滚操作：如果下载中断或更新某个仓库时发现分叉，
前面已经成功同步的仓库会保留；处理问题后可以重新运行。
`sync` 不导入或重置网页配置、已部署插件和录制数据。
可通过下面的命令查看本次清单中各仓库的版本和本地修改状态：

```bash
./src/robot_bringup/workspace.sh status
```

## 一个入口启动网页和机器人服务

原有 `registered_robot.launch.py` 现为统一入口，不需要另一套 launch 或每次手写机器人 ID：

```bash
cd ~/workspace/teleop_ws
source install/setup.bash
ros2 launch robot_bringup registered_robot.launch.py
```

访问 `http://机器人IP:7876/dashboard/#robots`。已有网页设置（目录、端口、ROS 域）继续沿用。
首次安装未选机器人时只运行网页。页面操作顺序：

1. 已有配置时直接选择机器人，已有插件不需要重新导入。
2. 首次使用时分别导入机械臂驱动、模型和可选夹爪 ZIP，再新建机器人配置；不需要整机 ZIP。
3. 修改参数后点击“保存配置”，通过校验后生成新版本。
4. 需要遥操作时勾选“同时启动遥操作”，按需选择是否启动已配置的相机。
5. 点击“开启机器人”，查看运行状态、驱动连接和启动日志。

此后重新运行同一命令会加载上次明确开启的机器人及遥操作/相机选项。
日常修改机器人参数的流程是：**修改参数 → 保存配置 → 点击“重启机器人”**。

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
网页自身的监听地址、ROS 域等系统设置与机器人参数不同，需要退出并重新启动整个 launch。
`./src/robot_bringup/workspace.sh web` 仍是只开网页的兼容入口，不提供可用的机器人进程控制按钮。

## 独立夹爪仓库与 OpenArmX 开发选项

`humanoid_gripper` 已关联到 [仓库清单](workspace.repos)，远端为
[HCEmbodiedIntelligence/humanoid_gripper](https://github.com/HCEmbodiedIntelligence/humanoid_gripper)，
源码位于 `src/humanoid_gripper`，是独立 Git 仓库，不再放在 `robot_bringup/packages` 中。

普通机器人只需在网页导入预编译的夹爪 ZIP，不必拉取夹爪源码。
需要开发 OpenArmX 适配器时，在工作区执行：

```bash
./src/robot_bringup/workspace.sh sync --profile openarmx
```

这会在 8 个通用仓库之外，额外拉取 `openarmx_driver`、`openarmx_description` 和 `humanoid_gripper`，
但不会自动启动 OpenArmX 硬件或生成整机 ZIP。之后保持原构建方式编译；
使用脚本构建时同样传 `--profile openarmx`，否则只构建默认通用包。

旧的 `src/humanoid_gripper` 如果是指向原内嵌包的软链接，OpenArmX 同步会先克隆成功，再替换这个链接。
默认通用同步仅清理已失效的旧夹爪链接，不因此拉取夹爪源码；其他目录和错误链接不会被覆盖。
迁移后编译需清除旧 CMake 路径缓存，前述 `--cmake-clean-cache` 已包含这一步。

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

修改后重新构建 `robot_bringup`，退出并重新启动整个统一 launch。
直接修改 launch 文件属于本地源码修改，后续同步时也会受到前述检查保护。
也支持通过启动参数配置：`vendor_package:=... vendor_launch_file:=... vendor_arguments:='{"key":"value"}'`。
参数值须为字符串；不接受 `$(...)` 表达式。厂商 launch 应直接管理自己的子进程，不应自行 daemonize 或启动脱离监管的服务。
这些服务在机器人子进程内启动，随网页按钮一起关闭/重启；不能作为网页的平级独立进程，否则按钮无法管理它们。
厂商包需事先安装并编译，不会自动下载；默认不启动任何特定厂商硬件。
OpenArmX 应填写实际验证过的启动参数，确保机械臂 7 轴控制器与夹爪分离，不可直接套用默认 8 轴机械臂控制器。

内部 `humanoid_manager/managed_robot.launch.py` 保留为隔离的子进程实现，用户无需单独运行。
旧的仅机器人集成可显式指定 `web:=false robot_id:=my_robot`，然后使用原组件开关。
默认遥操作关闭，相机开启；网页可选择。遥操作使用模型的 `hc_teleop_config` 启动 `hc_teleop_recv`，不启动旧接收端。
插件部署协议见 [docs/registering_robot.md](docs/registering_robot.md)。

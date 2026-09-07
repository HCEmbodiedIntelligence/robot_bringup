# 注册新机器人

`robot_bringup` 不维护机器人枚举，也不读取已安装的机器人专用 ROS 包。新机器人通过
`humanoid_manager` 导入两个独立插件，并在机器人页面生成内部组合清单：

1. `hardware_driver`：预编译的 `RobotDriverPlugin`、pluginlib 元数据及其驱动参数；
2. `robot_model`：motion/channel/tool 配置及运动学 URDF；
3. 内部组合清单：由管理器保存，只引用前两个插件 ID，不要求用户制作 ZIP。

目标机只安装核心包，不安装或编译厂商 driver、description、bringup 源码。ZIP schema、校验规则和
CLI 用法见
[`humanoid_manager/docs/deploying_plugins.md`](../../humanoid_manager/docs/deploying_plugins.md)。

## 一致性边界

打包前必须保证这些资源描述同一套逻辑关节及顺序：

- hardware-driver 插件中 driver YAML 的 `joint_names`；
- motion YAML 与 SDK YAML 的 joint groups；
- URDF 中的可动关节；
- 各 group 的上下限数组。

厂商名称、单位、方向和零位只放在 driver mapping 中。运动层只使用逻辑关节名和 SI 单位。
`humanoid_manager` 会在部署前交叉校验这些约束。

## 部署和启动

先导入驱动插件和模型插件，再在 `humanoid_manager` 网页的“机器人配置”中选择两者，填写
机器人 ID 和名称并创建配置：

```bash
ros2 run humanoid_manager humanoid_pluginctl.py deploy my-driver.zip
ros2 run humanoid_manager humanoid_pluginctl.py deploy my-model.zip
```

保存并应用后，管理器会生成并部署内部组合清单。网页同时配置关节、相机、底盘、夹爪和录制方案。

由通用 bringup 启动已注册机器人：

```bash
ros2 launch robot_bringup registered_robot.launch.py \
  robot_id:=my_robot_v1 \
  start_teleop:=false
```

`start_driver`、`start_motion`、`start_teleop` 和 `start_cameras` 控制网页已应用配置中的运行组件。
该入口委托给 `humanoid_manager/managed_robot.launch.py`，因此不会漏掉相机和配置状态节点。机器人专用的硬件上电、
CAN 初始化或厂商控制器启动不应写入这个通用 launch，由整机 supervisor 在外层编排。

## HC PICO 末端遥操作

模型插件声明 `resources.hc_teleop_config: resources/hc_teleop.yaml` 后，
`start_teleop:=true` 会启动 `hc_teleop_recv/hc_teleop_recv_node`，配置路径来自 manager 的解析结果。
接收器订阅 motion server 的实测 FK，通过 ServoP 发送末端目标；不启动原 HC 项目的 IK 或关节命令 mux。

```bash
ros2 launch robot_bringup registered_robot.launch.py \
  robot_id:=my_robot start_teleop:=true
```

接收器默认禁用，按 PICO 右手 A 或调用 `/hc_teleop_recv/set_enabled` 后，松开再按 Grip 开始控制。
旧的 `teleop_config` 不再受支持；所有遥操作配置统一使用 `hc_teleop_config`。
模型更换后按新 robot_id 重新启动即可，不在通用 launch 中添加机器人名称分支。

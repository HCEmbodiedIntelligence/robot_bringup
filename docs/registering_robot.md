# 注册新机器人

`robot_bringup` 不维护机器人枚举，也不读取已安装的机器人专用 ROS 包。新机器人通过
`humanoid_adapter_manager` 部署两个独立插件和一个组合清单：

1. `hardware_driver`：预编译的 `RobotDriverPlugin`、pluginlib 元数据及其驱动参数；
2. `robot_model`：motion/channel/tool 配置及运动学 URDF；
3. `robot_composition`：只引用前两个插件 ID，不包含代码或机器人资源。

目标机只安装核心包，不安装或编译厂商 driver、description、bringup 源码。ZIP schema、校验规则和
CLI 用法见
[`humanoid_adapter_manager/docs/deploying_plugins.md`](../../humanoid_adapter_manager/docs/deploying_plugins.md)。

## 一致性边界

打包前必须保证这些资源描述同一套逻辑关节及顺序：

- hardware-driver 插件中 driver YAML 的 `joint_names`；
- motion YAML 与 SDK YAML 的 joint groups；
- URDF 中的可动关节；
- 各 group 的上下限数组。

厂商名称、单位、方向和零位只放在 driver mapping 中。运动层只使用逻辑关节名和 SI 单位。
`humanoid_adapter_manager` 会在部署前交叉校验这些约束。

## 部署和启动

先部署驱动插件和模型插件，最后部署引用它们的组合清单：

```bash
ros2 run humanoid_adapter_manager humanoid_pluginctl.py deploy my-driver.zip
ros2 run humanoid_adapter_manager humanoid_pluginctl.py deploy my-model.zip
ros2 run humanoid_adapter_manager humanoid_pluginctl.py deploy my-composition.zip
ros2 run humanoid_adapter_manager humanoid_pluginctl.py resolve my_robot_v1
```

由通用 bringup 启动已注册机器人：

```bash
ros2 launch robot_bringup registered_robot.launch.py \
  robot_id:=my_robot_v1 \
  start_teleop:=false
```

`start_driver`、`start_motion` 和 `start_teleop` 只控制核心进程是否启动。机器人专用的硬件上电、
CAN 初始化或厂商控制器启动不应写入这个通用 launch，由整机 supervisor 在外层编排。

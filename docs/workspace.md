# 一次拉取、构建及管理器导入

`robot_bringup` 是工作区总入口。`workspace.repos` 记录仓库 URL 和版本；默认拉取 OpenArmX
所需的 10 个仓库。独立 ROS 包 `humanoid_gripper` 随本仓库保存在
`packages/humanoid_gripper`，同步会创建 `src/humanoid_gripper` 符号链接，构建时作为独立包编译。

机器人电脑要求 **Ubuntu 22.04、Intel/AMD x86-64、ROS 2 Humble**。预先安装 Git、
`python3-rosdep` 和 `python3-colcon-common-extensions`；私有仓库需要已有 GitHub SSH 访问权限。

## 新机器

在希望创建工作区的目录执行：

```bash
mkdir -p teleop_ws/src
git clone git@github.com:HCEmbodiedIntelligence/robot_bringup.git teleop_ws/src/robot_bringup
cd teleop_ws
./src/robot_bringup/workspace.sh setup --install-deps --jobs 2
```

这条 setup 命令按顺序拉取仓库、安装 ROS/SDK/网页依赖、构建 11 个 ROS 包，再生成
`deploy_artifacts/openarmx-<时间>/openarmx-v10-complete.zip`。SDK 依赖源码编译可能耗时较长；
系统依赖安装可能请求 sudo 密码。已有 `alg_dep` 时可加 `--sdk-source /path/to/alg_dep`。
系统依赖已安装的机器省略 `--install-deps`。

只需要拉代码，或只安装通用软件：

```bash
./src/robot_bringup/workspace.sh sync --profile openarmx
./src/robot_bringup/workspace.sh setup --profile core --install-deps
```

`core` 包含管理器、接收端、运动服务、通用驱动运行时、相机和接口包；`openarmx` 额外
构建 OpenArmX 驱动、官方模型及独立夹爪插件。旧 `HC-teleop-robotic`、`teleop_vr_recv`
和 MuJoCo 不参与这条真机软件链路。

## 在网页导入

```bash
./src/humanoid_manager/start_configurator.sh --host 0.0.0.0
```

在机器人局域网打开 `http://机器人IP:7876/dashboard/#robots`，点击“导入配置包”，选择
整机配置并上传 **openarmx-v10-complete.zip**，填写新的机器人 ID 和名称。无需解压或逐个
导入内部 ZIP。导入后可以编辑关节、夹爪、遥操作、相机等配置，保存并应用。
夹爪映射已填写，默认关闭，可按实机接线在页面启用。

单独的 `driver.zip`、`model.zip`、`gripper.zip` 用于单插件导入。整机包由管理器自身的
导出功能生成，并在临时目录中经过“导入 → 应用 → 解析”验证；打包不会覆盖当前机器人配置。

## 启动机器人

先按 OpenArmX 官方流程启动底层硬件和 ros2_control，使用发布目录中的
`openarmx_v10_split_controllers.yaml`：左右手臂各 7 个关节，左右夹爪使用独立控制器。
这个工作区的 `openarmx_driver` 是 Topic 适配器；官方硬件驱动、CAN 配置和电机控制参数
仍需在机器人电脑上准备，不由 setup 自动启动。

确认与硬件层使用相同 ROS Domain，再启动页面中已经应用的配置：

```bash
ROS_DOMAIN_ID=14 ./src/robot_bringup/scripts/start_robot.sh 你导入时填写的机器人ID
```

默认插件目录与管理器一致：优先已有 `/var/lib/humanoid-plugins`，否则
`~/.local/share/humanoid-plugins`。网页使用自定义目录时，启动命令追加
`plugin_root:=/同一个目录`。启动接收端后按右手 A 使能，松开再按 Grip 绑定实测起点。

## 更新与重新打包

```bash
./src/robot_bringup/workspace.sh sync
./src/robot_bringup/workspace.sh bundle --jobs 2
```

同步会先检查所有仓库是否有未提交修改或错误的 origin，更新只允许快进；不会自动 stash、
reset 或覆盖本地提交。`bundle` 总会先构建，再从本次 `install` 打包，避免复用旧驱动。
每次生成新目录，可通过 `--output /绝对路径/新目录` 指定位置；已有目录不覆盖。

`source-revisions.json` 记录各仓库提交、是否有本地修改以及产物 SHA-256；
`workspace.lock.repos` 锁定相同版本。可使用 `sync --manifest /path/to/workspace.lock.repos`
获取指定版本；含未提交修改的发布记录不能仅靠锁定清单复现。
`workspace.repos` 使用 JSON 语法的 YAML，可交给 `vcs import src`，但正常操作无需安装 vcstool。

`humanoid_manager` 的目录名是包名；其现有远端仍叫 `humanoid_adapter_manager`，清单已处理映射。
自定义模型模板与生成器位于自有 `openarmx_driver/deployment` 和 `tools/create_model_bundle.py`，
官方 `openarmx_description` 固定提交只提供 URDF 资源。

软件验收不会启动电机。上真机仍需核对关节零位与方向，并完成低速动作、输入断流和停止验证。

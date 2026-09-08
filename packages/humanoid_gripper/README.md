# humanoid_gripper

This package is the extensible collection of gripper drivers and protocol adapters. It is independent
from arm drivers, robot kinematics, the motion server, and the Web manager.

`humanoid_gripper/RosTopicGripperDriver` maps one or more logical grippers to configurable
vendor ROS topics. Per gripper it supports:

- command: `sensor_msgs/msg/JointState`, `std_msgs/msg/Float64`, or
  `std_msgs/msg/Float64MultiArray`;
- feedback: `sensor_msgs/msg/JointState` or `std_msgs/msg/Float64`;
- logical position limits, linear/angular units, direction, and zero offset.

Specialized SDK, CAN, Action, reused third-party drivers, or dexterous-hand plugins can be added
alongside this class while keeping the same `GripperDriverPlugin` runtime contract. Existing drivers
that already expose ROS topics can be reused through this adapter without changing their code.

The plugin is loaded by `humanoid_gripper_runtime_node`. Platform-facing commands and feedback use
named `sensor_msgs/msg/JointState` topics, so `hc_teleop_recv` never publishes to vendor endpoints.

The included `openarmx_v10_bimanual.yaml` is only a configuration profile for reusing the generic
topic adapter. `config/v10_controllers/openarmx_v10_split_controllers.yaml` supplies separate
seven-joint arm and one-joint gripper ros2_control controllers. Start the two gripper controllers
after OpenArmX bringup; this prevents the arm and gripper runtimes from claiming or publishing the
same command interface.

After an isolated build, create an importable manager bundle with:

```bash
python3 src/humanoid_gripper/tools/create_deployment_bundle.py \
  install/humanoid_gripper deploy_artifacts/openarmx-gripper.zip \
  --config openarmx_v10_bimanual.yaml \
  --plugin-id openarmx_v10_bimanual_gripper \
  --name "OpenArmX v10 bimanual grippers"
```

`config/ros_topic_gripper.yaml` is the editable deployment template. Build the package, then create
an importable `gripper_driver` ZIP with:

```bash
python3 tools/create_deployment_bundle.py \
  "$(ros2 pkg prefix humanoid_gripper)" humanoid-gripper.zip
```

Import that ZIP on the humanoid_manager robot page. The page copies the selected plugin into the
robot version and keeps logical names, vendor endpoints, limits, and teleoperation mapping in sync.

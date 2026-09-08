// Copyright 2026 czy
// SPDX-License-Identifier: LicenseRef-Proprietary

#ifndef HUMANOID_GRIPPER__ROS_TOPIC_GRIPPER_DRIVER_HPP_
#define HUMANOID_GRIPPER__ROS_TOPIC_GRIPPER_DRIVER_HPP_

#include <chrono>
#include <cstddef>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

#include "humanoid_driver_interface/ros2_gripper_driver_plugin.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "std_msgs/msg/float64.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"

namespace humanoid_gripper
{

// A configurable ROS transport adapter. It contains no robot- or gripper-model branches; each
// logical gripper selects its vendor command/feedback topic and message type in plugin parameters.
class RosTopicGripperDriver final :
  public humanoid_driver_interface::Ros2GripperDriverPlugin
{
public:
  RosTopicGripperDriver() = default;
  ~RosTopicGripperDriver() override = default;

  humanoid_driver_interface::DriverResult attachRosNode(rclcpp::Node & node) override;
  humanoid_driver_interface::DriverResult configure(
    const humanoid_driver_interface::GripperConfiguration & configuration) override;
  humanoid_driver_interface::DriverResult connect() override;
  humanoid_driver_interface::DriverResult disconnect() override;
  humanoid_driver_interface::DriverResult activate() override;
  humanoid_driver_interface::DriverResult deactivate() override;
  humanoid_driver_interface::DriverResult readGripperState(
    humanoid_driver_interface::GripperState & state) override;
  humanoid_driver_interface::DriverResult startGripperStream() override;
  humanoid_driver_interface::DriverResult writeGripperCommand(
    const humanoid_driver_interface::GripperCommand & command) override;
  humanoid_driver_interface::DriverResult stopGripperStream() override;
  humanoid_driver_interface::DriverResult stopAll() override;
  humanoid_driver_interface::DriverHealth health() override;

private:
  using Clock = std::chrono::steady_clock;
  using Mapping = humanoid_driver_interface::GripperMapping;
  using Result = humanoid_driver_interface::DriverResult;

  struct Endpoint
  {
    Mapping mapping;
    std::string command_topic;
    std::string command_type;
    std::string feedback_topic;
    std::string feedback_type;
    double minimum_position{0.0};
    double maximum_position{0.0};
    double measured_position{0.0};
    double measured_effort{0.0};
    Clock::time_point received_at{Clock::now()};
    bool have_feedback{false};
    rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr joint_publisher;
    rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr float_publisher;
    rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr array_publisher;
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_subscription;
    rclcpp::Subscription<std_msgs::msg::Float64>::SharedPtr float_subscription;
  };

  static double number(const std::string & label, const std::string & value);
  static bool finite(const std::vector<double> & values);
  static std::string parameter(
    const humanoid_driver_interface::GripperConfiguration & configuration,
    const std::string & logical_name, const std::string & key);
  void jointFeedback(std::size_t index, const sensor_msgs::msg::JointState & message);
  void floatFeedback(std::size_t index, const std_msgs::msg::Float64 & message);
  Result publishLocked(std::size_t index, double logical_position, double max_effort);
  std::size_t subscriberCount(const Endpoint & endpoint) const;
  bool feedbackFreshLocked(const Endpoint & endpoint, Clock::time_point now) const;
  Result rejectLocked(humanoid_driver_interface::DriverError error, std::string message);

  mutable std::mutex mutex_;
  rclcpp::Node * node_{nullptr};
  std::vector<std::unique_ptr<Endpoint>> endpoints_;
  std::unordered_map<std::string, std::size_t> by_logical_name_;
  std::chrono::duration<double> feedback_timeout_{0.5};
  std::chrono::duration<double> startup_grace_{15.0};
  Clock::time_point configured_at_{Clock::now()};
  std::string last_feedback_error_;
  std::string last_command_error_;
  bool configured_{false};
  bool connected_{false};
  bool active_{false};
  bool streaming_{false};
  bool holding_{true};
};

}  // namespace humanoid_gripper

#endif  // HUMANOID_GRIPPER__ROS_TOPIC_GRIPPER_DRIVER_HPP_

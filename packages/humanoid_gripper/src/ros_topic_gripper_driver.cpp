// Copyright 2026 czy
// SPDX-License-Identifier: LicenseRef-Proprietary

#include "humanoid_gripper/ros_topic_gripper_driver.hpp"

#include <algorithm>
#include <cmath>
#include <exception>
#include <stdexcept>
#include <unordered_set>
#include <utility>

#include "pluginlib/class_list_macros.hpp"

namespace hdi = humanoid_driver_interface;

namespace humanoid_gripper
{

RosTopicGripperDriver::Result RosTopicGripperDriver::attachRosNode(rclcpp::Node & node)
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (configured_) {
    return Result::failure(hdi::DriverError::kInvalidState, "attach ROS node before configure");
  }
  if (node_ != nullptr && node_ != &node) {
    return Result::failure(hdi::DriverError::kInvalidState, "a different ROS node is attached");
  }
  node_ = &node;
  return Result::success();
}

double RosTopicGripperDriver::number(const std::string & label, const std::string & value)
{
  std::size_t consumed = 0U;
  const double result = std::stod(value, &consumed);
  if (consumed != value.size() || !std::isfinite(result)) {
    throw std::invalid_argument(label + " must be a finite number");
  }
  return result;
}

std::string RosTopicGripperDriver::parameter(
  const hdi::GripperConfiguration & configuration, const std::string & logical_name,
  const std::string & key)
{
  const auto found = configuration.parameters.find(logical_name + "." + key);
  if (found == configuration.parameters.end() || found->second.empty()) {
    throw std::invalid_argument(logical_name + "." + key + " is required");
  }
  return found->second;
}

RosTopicGripperDriver::Result RosTopicGripperDriver::configure(
  const hdi::GripperConfiguration & configuration)
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (node_ == nullptr || connected_ || active_) {
    return Result::failure(hdi::DriverError::kInvalidState, "invalid configure lifecycle order");
  }
  std::unordered_set<std::string> accepted_parameters{"feedback_timeout_s", "startup_grace_s"};
  std::vector<std::unique_ptr<Endpoint>> endpoints;
  try {
    for (const auto & mapping : configuration.grippers) {
      auto endpoint = std::make_unique<Endpoint>();
      endpoint->mapping = mapping;
      endpoint->command_topic = parameter(configuration, mapping.logical_name, "command_topic");
      endpoint->command_type = parameter(configuration, mapping.logical_name, "command_type");
      endpoint->feedback_topic = parameter(configuration, mapping.logical_name, "feedback_topic");
      endpoint->feedback_type = parameter(configuration, mapping.logical_name, "feedback_type");
      endpoint->minimum_position = number(
        mapping.logical_name + ".min_position",
        parameter(configuration, mapping.logical_name, "min_position"));
      endpoint->maximum_position = number(
        mapping.logical_name + ".max_position",
        parameter(configuration, mapping.logical_name, "max_position"));
      if (endpoint->command_topic == endpoint->feedback_topic ||
        endpoint->minimum_position >= endpoint->maximum_position ||
        (endpoint->command_type != "joint_state" && endpoint->command_type != "float64" &&
        endpoint->command_type != "float64_multi_array") ||
        (endpoint->feedback_type != "joint_state" && endpoint->feedback_type != "float64"))
      {
        throw std::invalid_argument(mapping.logical_name + " has invalid ROS endpoint settings");
      }
      for (const auto * key : {"command_topic", "command_type", "feedback_topic", "feedback_type",
        "min_position", "max_position"})
      {
        accepted_parameters.insert(mapping.logical_name + "." + key);
      }
      endpoints.push_back(std::move(endpoint));
    }
    if (const auto found = configuration.parameters.find("feedback_timeout_s");
      found != configuration.parameters.end())
    {
      const auto seconds = number("feedback_timeout_s", found->second);
      if (seconds <= 0.0) {
        throw std::invalid_argument("feedback_timeout_s must be positive");
      }
      feedback_timeout_ = std::chrono::duration<double>(seconds);
    }
    if (const auto found = configuration.parameters.find("startup_grace_s");
      found != configuration.parameters.end())
    {
      const auto seconds = number("startup_grace_s", found->second);
      if (seconds <= 0.0) {
        throw std::invalid_argument("startup_grace_s must be positive");
      }
      startup_grace_ = std::chrono::duration<double>(seconds);
    }
    for (const auto & [key, value] : configuration.parameters) {
      (void)value;
      if (accepted_parameters.count(key) == 0U) {
        throw std::invalid_argument("unknown ROS gripper parameter '" + key + "'");
      }
    }

    for (std::size_t index = 0; index < endpoints.size(); ++index) {
      auto & endpoint = *endpoints[index];
      if (endpoint.command_type == "joint_state") {
        endpoint.joint_publisher = node_->create_publisher<sensor_msgs::msg::JointState>(
          endpoint.command_topic, rclcpp::QoS(10).reliable());
      } else if (endpoint.command_type == "float64") {
        endpoint.float_publisher = node_->create_publisher<std_msgs::msg::Float64>(
          endpoint.command_topic, rclcpp::QoS(10).reliable());
      } else {
        endpoint.array_publisher = node_->create_publisher<std_msgs::msg::Float64MultiArray>(
          endpoint.command_topic, rclcpp::QoS(10).reliable());
      }
      if (endpoint.feedback_type == "joint_state") {
        endpoint.joint_subscription = node_->create_subscription<sensor_msgs::msg::JointState>(
          endpoint.feedback_topic, rclcpp::SensorDataQoS(),
          [this, index](const sensor_msgs::msg::JointState::SharedPtr message) {
            jointFeedback(index, *message);
          });
      } else {
        endpoint.float_subscription = node_->create_subscription<std_msgs::msg::Float64>(
          endpoint.feedback_topic, rclcpp::SensorDataQoS(),
          [this, index](const std_msgs::msg::Float64::SharedPtr message) {
            floatFeedback(index, *message);
          });
      }
    }
  } catch (const std::exception & error) {
    return Result::failure(hdi::DriverError::kInvalidConfiguration, error.what());
  }

  endpoints_ = std::move(endpoints);
  by_logical_name_.clear();
  for (std::size_t index = 0; index < endpoints_.size(); ++index) {
    by_logical_name_.emplace(endpoints_[index]->mapping.logical_name, index);
  }
  configured_at_ = Clock::now();
  configured_ = true;
  connected_ = active_ = streaming_ = false;
  holding_ = true;
  last_feedback_error_.clear();
  last_command_error_.clear();
  return Result::success("ROS topic gripper driver configured");
}

RosTopicGripperDriver::Result RosTopicGripperDriver::connect()
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (!configured_ || connected_ || active_) {
    return Result::failure(hdi::DriverError::kInvalidState, "configure before connect");
  }
  connected_ = true;
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::disconnect()
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (active_) {
    return Result::failure(hdi::DriverError::kInvalidState, "deactivate before disconnect");
  }
  connected_ = false;
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::activate()
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (!connected_ || active_) {
    return Result::failure(hdi::DriverError::kInvalidState, "connect before activate");
  }
  active_ = true;
  holding_ = true;
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::deactivate()
{
  std::lock_guard<std::mutex> lock(mutex_);
  active_ = false;
  streaming_ = false;
  holding_ = true;
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::readGripperState(hdi::GripperState & state)
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (!active_ || !streaming_) {
    return Result::failure(hdi::DriverError::kNotActive, "gripper stream is inactive");
  }
  const auto now = Clock::now();
  for (const auto & endpoint : endpoints_) {
    if (!endpoint->have_feedback) {
      const auto error = now - configured_at_ < startup_grace_ ?
        hdi::DriverError::kNoFeedback : hdi::DriverError::kCommunication;
      return Result::failure(error, "awaiting feedback for " + endpoint->mapping.logical_name);
    }
    if (!feedbackFreshLocked(*endpoint, now)) {
      return Result::failure(
        hdi::DriverError::kCommunication,
        "stale feedback for " + endpoint->mapping.logical_name);
    }
  }
  state = {};
  state.sample_time = now;
  for (const auto & endpoint : endpoints_) {
    state.gripper_names.push_back(endpoint->mapping.logical_name);
    state.positions.push_back(endpoint->measured_position);
    state.efforts.push_back(endpoint->measured_effort);
    state.sample_time = std::min(state.sample_time, endpoint->received_at);
  }
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::startGripperStream()
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (!active_) {
    return Result::failure(hdi::DriverError::kNotActive, "activate before starting stream");
  }
  streaming_ = true;
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::writeGripperCommand(
  const hdi::GripperCommand & command)
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (!active_ || !streaming_) {
    return rejectLocked(hdi::DriverError::kNotActive, "gripper stream is inactive");
  }
  const auto count = command.gripper_names.size();
  if (count == 0U || command.positions.size() != count ||
    command.vendor_gripper_names.size() != count ||
    (!command.max_efforts.empty() && command.max_efforts.size() != count) ||
    !finite(command.positions) || !finite(command.max_efforts))
  {
    return rejectLocked(hdi::DriverError::kRejectedCommand, "invalid gripper command fields");
  }
  std::unordered_set<std::string> names;
  for (std::size_t command_index = 0; command_index < count; ++command_index) {
    const auto found = by_logical_name_.find(command.gripper_names[command_index]);
    if (found == by_logical_name_.end() ||
      !names.insert(command.gripper_names[command_index]).second)
    {
      return rejectLocked(hdi::DriverError::kRejectedCommand, "unknown or duplicate gripper");
    }
    const auto & endpoint = *endpoints_[found->second];
    if (command.vendor_gripper_names[command_index] != endpoint.mapping.vendor_name ||
      command.positions[command_index] < endpoint.minimum_position ||
      command.positions[command_index] > endpoint.maximum_position)
    {
      return rejectLocked(
        hdi::DriverError::kRejectedCommand, "gripper name or configured position limit mismatch");
    }
  }
  for (std::size_t command_index = 0; command_index < count; ++command_index) {
    const auto endpoint_index = by_logical_name_.at(command.gripper_names[command_index]);
    const double effort = command.max_efforts.empty() ? 0.0 : command.max_efforts[command_index];
    const auto result = publishLocked(endpoint_index, command.positions[command_index], effort);
    if (!result) {
      return result;
    }
  }
  holding_ = false;
  last_command_error_.clear();
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::stopGripperStream()
{
  std::lock_guard<std::mutex> lock(mutex_);
  streaming_ = false;
  return Result::success();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::stopAll()
{
  std::lock_guard<std::mutex> lock(mutex_);
  holding_ = true;
  for (std::size_t index = 0; index < endpoints_.size(); ++index) {
    if (!endpoints_[index]->have_feedback) {
      return rejectLocked(
        hdi::DriverError::kNoFeedback,
        "cannot hold " + endpoints_[index]->mapping.logical_name + " before feedback");
    }
  }
  for (std::size_t index = 0; index < endpoints_.size(); ++index) {
    const auto result = publishLocked(index, endpoints_[index]->measured_position, 0.0);
    if (!result) {
      return result;
    }
  }
  last_command_error_.clear();
  return Result::success("holding measured gripper positions");
}

hdi::DriverHealth RosTopicGripperDriver::health()
{
  std::lock_guard<std::mutex> lock(mutex_);
  hdi::DriverHealth result;
  result.connected = connected_;
  result.active = active_;
  result.details["configured"] = configured_ ? "true" : "false";
  result.details["streaming"] = streaming_ ? "true" : "false";
  result.details["holding"] = holding_ ? "true" : "false";
  result.details["last_feedback_error"] = last_feedback_error_;
  result.details["last_command_error"] = last_command_error_;
  if (!configured_) {
    result.level = hdi::HealthLevel::kStale;
    result.message = "ROS topic gripper plugin is not configured";
    return result;
  }
  const auto now = Clock::now();
  bool all_feedback = true;
  bool all_endpoints = true;
  for (const auto & endpoint : endpoints_) {
    const bool fresh = feedbackFreshLocked(*endpoint, now);
    const auto subscribers = subscriberCount(*endpoint);
    result.details[endpoint->mapping.logical_name + ".feedback_fresh"] = fresh ? "true" : "false";
    result.details[endpoint->mapping.logical_name + ".command_subscribers"] =
      std::to_string(subscribers);
    all_feedback = all_feedback && fresh;
    all_endpoints = all_endpoints && subscribers > 0U;
  }
  if (!all_feedback) {
    const bool grace = now - configured_at_ < startup_grace_;
    result.level = grace ? hdi::HealthLevel::kWarning : hdi::HealthLevel::kStale;
    result.communication_ok = grace;
    result.message = grace ? "awaiting initial gripper feedback" : "gripper feedback is stale";
  } else {
    result.communication_ok = true;
    result.level = all_endpoints && active_ && streaming_ ?
      hdi::HealthLevel::kOk : hdi::HealthLevel::kWarning;
    result.message = all_endpoints ? "ROS topic gripper driver operational" :
      "one or more gripper command topics have no subscriber";
  }
  return result;
}

void RosTopicGripperDriver::jointFeedback(
  const std::size_t index, const sensor_msgs::msg::JointState & message)
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (index >= endpoints_.size() || message.name.size() != message.position.size() ||
    (!message.effort.empty() && message.effort.size() != message.name.size()) ||
    !finite(message.position) || !finite(message.effort))
  {
    last_feedback_error_ = "invalid gripper JointState feedback";
    return;
  }
  auto & endpoint = *endpoints_[index];
  if (message.name.size() != std::unordered_set<std::string>(
      message.name.begin(), message.name.end()).size() ||
    std::count(message.name.begin(), message.name.end(), endpoint.mapping.vendor_name) != 1)
  {
    last_feedback_error_ = "gripper JointState is missing or repeats the configured vendor name";
    return;
  }
  const auto message_index = static_cast<std::size_t>(
    std::find(message.name.begin(), message.name.end(), endpoint.mapping.vendor_name) -
    message.name.begin());
  endpoint.measured_position = endpoint.mapping.vendor_to_logical_scale *
    message.position[message_index] + endpoint.mapping.vendor_to_logical_offset;
  endpoint.measured_effort = message.effort.empty() ? 0.0 :
    message.effort[message_index] / endpoint.mapping.vendor_to_logical_scale;
  endpoint.received_at = Clock::now();
  endpoint.have_feedback = true;
  last_feedback_error_.clear();
}

void RosTopicGripperDriver::floatFeedback(
  const std::size_t index, const std_msgs::msg::Float64 & message)
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (index >= endpoints_.size() || !std::isfinite(message.data)) {
    last_feedback_error_ = "invalid Float64 gripper feedback";
    return;
  }
  auto & endpoint = *endpoints_[index];
  endpoint.measured_position = endpoint.mapping.vendor_to_logical_scale * message.data +
    endpoint.mapping.vendor_to_logical_offset;
  endpoint.measured_effort = 0.0;
  endpoint.received_at = Clock::now();
  endpoint.have_feedback = true;
  last_feedback_error_.clear();
}

RosTopicGripperDriver::Result RosTopicGripperDriver::publishLocked(
  const std::size_t index, const double logical_position, const double max_effort)
{
  auto & endpoint = *endpoints_.at(index);
  const double vendor_position =
    (logical_position - endpoint.mapping.vendor_to_logical_offset) /
    endpoint.mapping.vendor_to_logical_scale;
  try {
    if (endpoint.joint_publisher) {
      sensor_msgs::msg::JointState message;
      message.header.stamp = node_->now();
      message.name = {endpoint.mapping.vendor_name};
      message.position = {vendor_position};
      message.effort = {max_effort};
      endpoint.joint_publisher->publish(message);
    } else if (endpoint.float_publisher) {
      std_msgs::msg::Float64 message;
      message.data = vendor_position;
      endpoint.float_publisher->publish(message);
    } else if (endpoint.array_publisher) {
      std_msgs::msg::Float64MultiArray message;
      message.data = {vendor_position};
      endpoint.array_publisher->publish(message);
    } else {
      return rejectLocked(hdi::DriverError::kCommunication, "gripper publisher is unavailable");
    }
  } catch (const std::exception & error) {
    return rejectLocked(hdi::DriverError::kCommunication, error.what());
  }
  return Result::success();
}

std::size_t RosTopicGripperDriver::subscriberCount(const Endpoint & endpoint) const
{
  if (endpoint.joint_publisher) {
    return endpoint.joint_publisher->get_subscription_count();
  }
  if (endpoint.float_publisher) {
    return endpoint.float_publisher->get_subscription_count();
  }
  return endpoint.array_publisher ? endpoint.array_publisher->get_subscription_count() : 0U;
}

bool RosTopicGripperDriver::feedbackFreshLocked(
  const Endpoint & endpoint, const Clock::time_point now) const
{
  return endpoint.have_feedback && now >= endpoint.received_at &&
         now - endpoint.received_at <= feedback_timeout_;
}

bool RosTopicGripperDriver::finite(const std::vector<double> & values)
{
  return std::all_of(
    values.begin(), values.end(), [](const double value) {return std::isfinite(value);});
}

RosTopicGripperDriver::Result RosTopicGripperDriver::rejectLocked(
  const hdi::DriverError error, std::string message)
{
  last_command_error_ = message;
  return Result::failure(error, std::move(message));
}

}  // namespace humanoid_gripper

PLUGINLIB_EXPORT_CLASS(
  humanoid_gripper::RosTopicGripperDriver,
  humanoid_driver_interface::GripperDriverPlugin)

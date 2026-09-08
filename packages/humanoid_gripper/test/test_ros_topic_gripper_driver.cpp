// Copyright 2026 czy
// SPDX-License-Identifier: LicenseRef-Proprietary

#include <chrono>
#include <functional>
#include <memory>
#include <thread>
#include <vector>

#include <gtest/gtest.h>

#include "rclcpp/executors/single_threaded_executor.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"

#include "humanoid_gripper/ros_topic_gripper_driver.hpp"

namespace hdi = humanoid_driver_interface;
namespace hg = humanoid_gripper;
using namespace std::chrono_literals;

namespace
{

class RosTopicGripperDriverTest : public ::testing::Test
{
protected:
  static void SetUpTestSuite()
  {
    int argc = 0;
    rclcpp::init(argc, nullptr);
  }

  static void TearDownTestSuite()
  {
    rclcpp::shutdown();
  }

  void SetUp() override
  {
    node_ = std::make_shared<rclcpp::Node>("ros_topic_gripper_driver_test");
    executor_.add_node(node_);
    feedback_ = node_->create_publisher<sensor_msgs::msg::JointState>(
      "/test_gripper/state", rclcpp::SensorDataQoS());
    commands_ = node_->create_subscription<std_msgs::msg::Float64MultiArray>(
      "/test_gripper/command", rclcpp::QoS(10).reliable(),
      [this](const std_msgs::msg::Float64MultiArray::SharedPtr message) {
        received_.push_back(*message);
      });
  }

  void TearDown() override
  {
    executor_.remove_node(node_);
    commands_.reset();
    feedback_.reset();
    node_.reset();
  }

  hdi::GripperConfiguration configuration() const
  {
    hdi::GripperConfiguration result;
    result.grippers = {{"tool", "vendor_finger", "m", -2.0, 0.1}};
    result.parameters = {
      {"tool.command_topic", "/test_gripper/command"},
      {"tool.command_type", "float64_multi_array"},
      {"tool.feedback_topic", "/test_gripper/state"},
      {"tool.feedback_type", "joint_state"},
      {"tool.min_position", "0.0"},
      {"tool.max_position", "0.1"},
      {"feedback_timeout_s", "0.25"},
      {"startup_grace_s", "1.0"},
    };
    return result;
  }

  void spinUntil(const std::function<bool()> & predicate)
  {
    const auto deadline = std::chrono::steady_clock::now() + 500ms;
    while (!predicate() && std::chrono::steady_clock::now() < deadline) {
      executor_.spin_some();
      std::this_thread::sleep_for(1ms);
    }
  }

  std::shared_ptr<rclcpp::Node> node_;
  rclcpp::executors::SingleThreadedExecutor executor_;
  rclcpp::Publisher<sensor_msgs::msg::JointState>::SharedPtr feedback_;
  rclcpp::Subscription<std_msgs::msg::Float64MultiArray>::SharedPtr commands_;
  std::vector<std_msgs::msg::Float64MultiArray> received_;
};

TEST_F(RosTopicGripperDriverTest, ConvertsFeedbackCommandsLimitsAndSafeHold)
{
  hg::RosTopicGripperDriver driver;
  ASSERT_TRUE(driver.attachRosNode(*node_));
  ASSERT_TRUE(driver.configure(configuration()));
  ASSERT_TRUE(driver.connect());
  ASSERT_TRUE(driver.activate());
  ASSERT_TRUE(driver.startGripperStream());

  hdi::GripperState state;
  EXPECT_EQ(driver.readGripperState(state).error, hdi::DriverError::kNoFeedback);

  sensor_msgs::msg::JointState feedback;
  feedback.name = {"unrelated", "vendor_finger"};
  feedback.position = {5.0, 0.02};
  feedback.effort = {0.0, 4.0};
  feedback_->publish(feedback);
  spinUntil([&driver, &state]() {return static_cast<bool>(driver.readGripperState(state));});

  ASSERT_TRUE(driver.readGripperState(state));
  ASSERT_EQ(state.gripper_names, (std::vector<std::string>{"tool"}));
  EXPECT_NEAR(state.positions[0], 0.06, 1e-12);
  EXPECT_NEAR(state.efforts[0], -2.0, 1e-12);

  hdi::GripperCommand command;
  command.gripper_names = {"tool"};
  command.vendor_gripper_names = {"vendor_finger"};
  command.positions = {0.08};
  ASSERT_TRUE(driver.writeGripperCommand(command));
  spinUntil([this]() {return received_.size() == 1U;});
  ASSERT_EQ(received_.size(), 1U);
  ASSERT_EQ(received_[0].data.size(), 1U);
  EXPECT_NEAR(received_[0].data[0], 0.01, 1e-12);

  command.positions = {0.11};
  EXPECT_EQ(driver.writeGripperCommand(command).error, hdi::DriverError::kRejectedCommand);

  ASSERT_TRUE(driver.stopAll());
  spinUntil([this]() {return received_.size() == 2U;});
  ASSERT_EQ(received_.size(), 2U);
  EXPECT_NEAR(received_[1].data[0], 0.02, 1e-12);
}

}  // namespace

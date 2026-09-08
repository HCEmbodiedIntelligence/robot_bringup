// Copyright 2026 czy
// SPDX-License-Identifier: LicenseRef-Proprietary

#include <gtest/gtest.h>

#include "humanoid_driver_interface/gripper_driver_plugin.hpp"
#include "pluginlib/class_loader.hpp"

TEST(HumanoidGripper, LoadsRosTopicPlugin)
{
  pluginlib::ClassLoader<humanoid_driver_interface::GripperDriverPlugin> loader(
    "humanoid_driver_interface", "humanoid_driver_interface::GripperDriverPlugin");
  const auto plugin = loader.createSharedInstance(
    "humanoid_gripper/RosTopicGripperDriver");
  ASSERT_NE(plugin, nullptr);
}

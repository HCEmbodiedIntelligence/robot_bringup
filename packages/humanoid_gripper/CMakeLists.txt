cmake_minimum_required(VERSION 3.8)
project(humanoid_gripper)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(ament_cmake REQUIRED)
find_package(humanoid_driver_interface REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(std_msgs REQUIRED)

add_library(humanoid_ros_topic_gripper_driver SHARED
  src/ros_topic_gripper_driver.cpp)
target_include_directories(humanoid_ros_topic_gripper_driver PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_compile_options(humanoid_ros_topic_gripper_driver PRIVATE -Wall -Wextra -Wpedantic)
ament_target_dependencies(humanoid_ros_topic_gripper_driver
  humanoid_driver_interface
  pluginlib
  rclcpp
  sensor_msgs
  std_msgs)

pluginlib_export_plugin_description_file(
  humanoid_driver_interface plugins/gripper_plugins.xml)

install(TARGETS humanoid_ros_topic_gripper_driver
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)
install(DIRECTORY include/ DESTINATION include)
install(DIRECTORY config plugins DESTINATION share/${PROJECT_NAME})
install(FILES README.md DESTINATION share/${PROJECT_NAME})
install(PROGRAMS tools/create_deployment_bundle.py DESTINATION lib/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_plugin_loading test/test_plugin_loading.cpp)
  ament_target_dependencies(test_plugin_loading humanoid_driver_interface pluginlib)

  ament_add_gtest(test_ros_topic_gripper_driver test/test_ros_topic_gripper_driver.cpp)
  target_link_libraries(test_ros_topic_gripper_driver humanoid_ros_topic_gripper_driver)
  ament_target_dependencies(test_ros_topic_gripper_driver
    humanoid_driver_interface
    rclcpp
    sensor_msgs
    std_msgs)
endif()

ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(
  humanoid_driver_interface
  pluginlib
  rclcpp
  sensor_msgs
  std_msgs)

ament_package()

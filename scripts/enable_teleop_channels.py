#!/usr/bin/env python3
"""Enable both OpenArmX VR channels after their services become available."""

import time

import rclpy
from rclpy.node import Node
from std_srvs.srv import SetBool


SERVICE_NAMES = (
    "/channels/left_arm/set_enabled",
    "/channels/right_arm/set_enabled",
)
SERVICE_TIMEOUT_SEC = 45.0
CALL_TIMEOUT_SEC = 10.0


def enable_channel(node: Node, service_name: str) -> None:
    client = node.create_client(SetBool, service_name)
    deadline = time.monotonic() + SERVICE_TIMEOUT_SEC
    while rclpy.ok() and not client.wait_for_service(timeout_sec=1.0):
        if time.monotonic() >= deadline:
            raise RuntimeError(f"timed out waiting for {service_name}")

    request = SetBool.Request()
    request.data = True
    future = client.call_async(request)
    rclpy.spin_until_future_complete(node, future, timeout_sec=CALL_TIMEOUT_SEC)
    if not future.done() or future.result() is None:
        raise RuntimeError(f"timed out calling {service_name}")
    if not future.result().success:
        raise RuntimeError(
            f"{service_name} rejected enable request: {future.result().message}"
        )
    node.get_logger().info(f"enabled {service_name}")


def main() -> None:
    rclpy.init()
    node = Node("openarmx_teleop_channel_enabler")
    exit_code = 0
    try:
        for service_name in SERVICE_NAMES:
            enable_channel(node, service_name)
        node.get_logger().info(
            "both VR channels are enabled; release each Grip once before binding"
        )
    except Exception as error:  # launch helper must report a nonzero process result
        node.get_logger().error(str(error))
        exit_code = 1
    finally:
        node.destroy_node()
        rclpy.shutdown()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

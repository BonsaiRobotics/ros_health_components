#!/usr/bin/env python3

import pytest
import unittest
import time

import rclpy

from launch import LaunchDescription
from launch_ros.actions import Node
from launch_testing.actions import ReadyToTest
from rclpy.qos import QoSProfile
# Import duration
from rclpy.duration import Duration


from std_msgs.msg import Bool
from diagnostic_msgs.msg import DiagnosticArray
import threading


qos_profile_with_deadline = QoSProfile(
    depth=10,
    deadline=Duration(seconds=0, nanoseconds=100000000)
)


@pytest.mark.launch_test
def generate_test_description():
    # Initialize with default params
    device_under_test = Node(
        package='rosgraph_monitor',
        executable='rosgraph_monitor_node',
        name='rosgraph_monitor',
        output='screen',
        arguments=['--ros-args', '--log-level', 'DEBUG'],
    )

    context = {'device_under_test': device_under_test}
    return (LaunchDescription([device_under_test,
                               ReadyToTest()]),  context)


class TestProcessOutput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Initialize the ROS context for the test node
        rclpy.init()

    @classmethod
    def tearDownClass(cls):
        # Shutdown the ROS context
        rclpy.shutdown()

    def setUp(self):
        # Create a ROS node for tests
        self.diagnostics = []
        self.diagnostics_agg_msgs = []
        self.topic_statistics = []
        self.publisher_node = rclpy.create_node('publisher_node')
        self.subscriber_node = rclpy.create_node('subscriber_node')

        self.executor = rclpy.executors.MultiThreadedExecutor()
        self.executor.add_node(self.publisher_node)
        self.executor.add_node(self.subscriber_node)

        self.dummy_publisher = self.publisher_node.create_publisher(
            Bool, '/bool_publisher', qos_profile_with_deadline)
        timer_period = 1.0  # seconds
        self.publishr_timer = self.publisher_node.create_timer(
            timer_period, self.publisher_callback)

        self.spin_thread = threading.Thread(target=self.executor.spin)
        self.spin_thread.start()

    def publisher_callback(self):
        msg = Bool()
        msg.data = True
        self.dummy_publisher.publish(msg)

    def tearDown(self):
        self.executor.shutdown()
        self.spin_thread.join()
        self.subscriber_node.destroy_node()
        self.publisher_node.destroy_node()

    def test_health_monitor_diagnostics(self):
        sub = self.subscriber_node.create_subscription(
            DiagnosticArray, '/diagnostics_agg', lambda msg: self.diagnostics_agg_msgs.append(msg), 1)

        end_time = time.time() + 5
        while time.time() < end_time:
            rclpy.spin_once(self.publisher_node, timeout_sec=0.1)

        self.subscriber_node.destroy_subscription(sub)

        self.assertGreater(
            len(self.diagnostics_agg_msgs), 0, "There should be at least one /diagnostics_agg message")

        last_msg = self.diagnostics_agg_msgs[-1]
        self.assertTrue(all([status.level == 0 for status in last_msg.status]),
                        "All diagnostic statuses should be healthy")

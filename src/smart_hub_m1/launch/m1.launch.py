"""M1 only; no bus/coordinator/safety or motor publishers."""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('scenario', default_value='s1'),
        Node(package='smart_hub_m1', executable='synthetic_tracks', output='screen',
             parameters=[{'scenario': LaunchConfiguration('scenario')}]),
        Node(package='smart_hub_m1', executable='passenger_detector', output='screen',
             parameters=[{'input_mode': 'synthetic'}]),
        Node(package='smart_hub_m1', executable='demand_predictor', output='screen'),
    ])

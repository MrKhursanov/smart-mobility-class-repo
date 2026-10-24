from glob import glob
from setuptools import find_packages, setup
setup(
    name='smart_hub_m1', version='0.1.0', packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/smart_hub_m1']),
        ('share/smart_hub_m1', ['package.xml']),
        ('share/smart_hub_m1/launch', glob('launch/*.py')),
        ('share/smart_hub_m1/config', glob('config/*')),
        ('share/smart_hub_m1/models', glob('models/*.json')),
        ('share/smart_hub_m1/data', glob('data/*.csv')),
    ], install_requires=['setuptools', 'numpy'], tests_require=['pytest'], zip_safe=True,
    maintainer='M1 student', maintainer_email='student@example.com',
    description='M1 passenger perception and forecasting', license='MIT',
    entry_points={'console_scripts': [
        'passenger_detector = smart_hub_m1.nodes:detector_main',
        'demand_predictor = smart_hub_m1.nodes:predictor_main',
        'synthetic_tracks = smart_hub_m1.nodes:synthetic_main',
        'video_source = smart_hub_m1.nodes:video_main',
    ]},
)

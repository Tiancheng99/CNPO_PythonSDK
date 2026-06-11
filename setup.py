# SDKPython/setup.py
from setuptools import setup, find_packages

setup(
    name="robot_sdk_v2_test",
    version="0.1",
    packages=find_packages(),
    zip_safe=False,
    install_requires=[
        "pymodbus==3.11.3",
        "numpy>=1.23",
        "scipy>=1.10",
    ]
)


# TODO 使用时,先切换到 SDKPython 目录下,然后执行可编辑安装 ‘pip install -e .’ 
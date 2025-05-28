# setup.py
from setuptools import setup, find_packages
import os

with open(os.path.join(os.path.dirname(__file__), 'README.txt'), 'r') as f:
    description = f.read()

setup(
    name="autobot",
    version="0.1.0",
    description=description,
    packages=find_packages(),
    python_requires=">=3.10",
)


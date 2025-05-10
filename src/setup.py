# setup.py
from setuptools import setup, find_packages

setup(
    name="autobot",
    version="0.1.0",
    package_dir={"": "src"},           # Tout ce qui est dans src/ devient module racine
    packages=find_packages(where="src"),  
    py_modules=[                       # Fais aussi des .py de src/ des modules top‑level
        __import__("glob").glob("src/*.py").__iter__().__next__().split("/")[-1].split(".")[0]
        for _ in __import__("glob").glob("src/*.py")
    ]
)


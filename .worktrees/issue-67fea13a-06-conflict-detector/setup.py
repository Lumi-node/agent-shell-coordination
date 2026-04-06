"""Setup configuration for multi-agent-terminal package."""
from setuptools import setup, find_packages

setup(
    name="multi-agent-terminal",
    version="0.1.0",
    description="A distributed system enabling autonomous AI agents to collaboratively execute shell commands",
    author="Claude Code",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[],
    entry_points={
        "console_scripts": [
            "mat-coordinate=mat.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)

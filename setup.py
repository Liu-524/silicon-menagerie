#!/usr/bin/env python
from setuptools import setup

setup(
    name="saycam_models",
    version="1.0",
    author="Emin Orhan",
    description="Model definition and utilities from silicon-menagerie",
    py_modules=["saycam_utils"],
    python_requires=">=3.9",
    license="MIT",
    zip_safe=True,
)

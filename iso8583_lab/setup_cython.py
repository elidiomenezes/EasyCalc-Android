"""Compile the reusable protocol and rules modules with Cython."""

from setuptools import setup
from Cython.Build import cythonize


setup(
    name="iso8583-lab-core",
    ext_modules=cythonize(
        ["iso8583_common.py", "rules_engine.py"],
        compiler_directives={"language_level": "3"},
    ),
)

#!/usr/bin/env python
from codecs import open
import os
from setuptools import setup

metadata = {}
with open(os.path.join("pyhuml", "__metadata__.py")) as f:
    exec(f.read(), metadata)

with open("README.md", encoding="utf-8") as f:
    README = f.read()

setup(
    name="pyhuml",
    version=metadata["__version__"],
    description="An experimental parser and dumper for the HUML (Human-oriented Markup Language) format.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Kailash Nadh",
    author_email="kailash@nadh.in",
    url="https://huml.io",
    packages=['pyhuml'],
    include_package_data=True,
    install_requires=[],
    python_requires=">=3.6",
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Topic :: Text Processing :: Markup",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    keywords=["huml", "markup", "parser", "stringifier"],
)

#!/usr/bin/env python

# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------

"""
python setup script
"""
import sys
from setuptools import setup, find_packages

__version__ = "1.4.0"
__NAME__ = "hds"

if '--wheelversion' in sys.argv:
    index = sys.argv.index('--wheelversion')
    sys.argv.pop(index)  # Removes the '--wheelversion'
    # Returns the element after the '--wheelversion'
    __version__ = sys.argv.pop(index)
# The foo is now ready to use for the setup

if '--wheelname' in sys.argv:
    index = sys.argv.index('--wheelname')
    sys.argv.pop(index)  # Removes the '--wheelname'
    # Returns the element after the '--wheelname'
    __NAME__ = sys.argv.pop(index)

with open(file="README.md", mode="r", encoding='utf-8') as fh:
    long_description = fh.read()


setup(
    name=__NAME__,
    version=__version__,
    author="Microsoft Cloud for Healthcare",
    description="Healthcare Data Platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    include_package_data=True,
    packages=find_packages('src'),
    package_dir={'': 'src'}

)

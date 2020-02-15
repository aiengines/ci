#!/usr/bin/env python3


from setuptools import setup, find_packages

VERSION = 0.1
MIN_PYTHON_VERSION = '>=3.6.*'

requirements = [
    'boto3',
    'awacs',
    'troposphere'
]

setup(
    name='awsutils',
    version=VERSION,
    author='Pedro Larroy',
    url='https://github.com/aiengines/ci/',
    description='AWS utilities',
    license='Apache',

    # Package info
    packages=find_packages(),
    zip_safe=True,
    include_package_data=True,
    install_requires=requirements,
    python_requires=MIN_PYTHON_VERSION
)

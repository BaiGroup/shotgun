#!/usr/bin/env python

from __future__ import unicode_literals
from setuptools import find_packages, setup
from shotgun import APP_NAME, APP_VERSION


if __name__ == '__main__':
    setup(
        name=APP_NAME,
        version=APP_VERSION,
        author='Peng Bai',
        author_email='peng@bai.com',
        url='https://pypi.python.org/pypi/shotgun',
        description='Shotgun',
        long_description=__doc__,
        install_requires=[
            'Fabric >= 2.0',
            'future',
            'invoke',
            'ruamel.yaml',
            'SQLAlchemy'
        ],
        license='N/A',
        classifiers=[
            'Development Status :: 4 - Beta',
            'Intended Audience :: Science/Research',
            'License :: N/A',
            'Operating System :: OS Independent',
            'Programming Language :: Python :: 2',
            'Programming Language :: Python :: 2.7',
            'Programming Language :: Python :: 3',
            'Programming Language :: Python :: 3.3',
            'Programming Language :: Python :: 3.4',
            'Programming Language :: Python :: 3.5',
            'Programming Language :: Python :: 3.6',
            'Topic :: Software Development :: Libraries :: Python Modules',
        ],
        packages=find_packages(),
        include_package_data=True,
        entry_points={
            'console_scripts': ['shotgun = shotgun.commands:program.run']
        },
    )

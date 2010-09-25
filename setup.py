#!/usr/bin/env python

import os
from glob import glob
from postr import __version__
from setuptools import setup, find_packages

setup(name='Postr',
      version=__version__,
      description='Yupoo Uploader',
      author='Ross Burton',
      author_email='ross@burtonini.com',
      url='http://www.burtonini.com/',

      scripts=['script/postr'],
      packages=find_packages(),
      package_data={'postr': ['postr.glade']},
      data_files=[
          ('share/applications', ['data/postr.desktop']),
          ('share/icons/hicolor/16x16/apps', glob('data/16x16/*.png')),
          ('share/icons/hicolor/22x22/apps', glob('data/22x22/*.png')),
          ('share/icons/hicolor/24x24/apps', glob('data/24x24/*.png')),
          ('share/icons/hicolor/32x32/apps', glob('data/32x32/*.png')),
          ('share/icons/hicolor/scalable/apps', glob('data/scalable/*.svg')),
          ('lib/nautilus/extensions-2.0/python', ['nautilus/postrExtension.py']),
      ]
)

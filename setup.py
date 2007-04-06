#!/usr/bin/env python

from distutils.core import setup
from glob import glob

setup(name='Postr',
      version='0.5',
      description='Flickr Uploader',
      author='Ross Burton',
      author_email='ross@burtonini.com',
      url='http://www.burtonini.com/',

      scripts=['postr'],
      package_dir={'postr': 'src'},
      packages=['postr'],
      package_data={'postr': ['postr.glade']},
      data_files=[('share/applications', ['src/postr.desktop']),
                  ('lib/nautilus/extensions-1.0/python', ['nautilus/postrExtension.py']),
                  ('share/icons/hicolor/16x16/apps', glob('icons/16x16/*')),
                  ('share/icons/hicolor/22x22/apps', glob('icons/22x22/*')),
                  ('share/icons/hicolor/32x32/apps', glob('icons/32x32/*')),
                  ('share/icons/hicolor/scalable/apps', glob('icons/scalable/*')),
                  ],
      
      )


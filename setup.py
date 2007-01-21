#!/usr/bin/env python

from distutils.core import setup

setup(name='Postr',
      version='0.4',
      description='Flickr Uploader',
      author='Ross Burton',
      author_email='ross@burtonini.com',
      url='http://www.burtonini.com/',

      scripts=['postr'],
      package_dir={'postr': 'src'},
      packages=['postr'],
      package_data={'postr': ['postr.glade']},
      data_files=[('share/applications', ['src/postr.desktop']),
                  ('lib/nautilus/extensions-1.0/python', ['nautilus/postrExtension.py'])
                  ]
      )

#!/usr/bin/env python

import os
from distutils.core import setup
from distutils.command.install_data import install_data
from glob import glob
from src import __version__


class InstallData(install_data):
    def run(self):
        self.data_files.extend(self._nautilus_plugin())
        install_data.run(self)

    def _nautilus_plugin(self):
        files = []
        cmd = os.popen('pkg-config --variable=pythondir nautilus-python', 'r')
        res = cmd.readline().strip()
        ret = cmd.close()

        if ret is None:
            dest = res[5:]
            files.append((dest, ['nautilus/postrExtension.py']))

        return files


setup(name='Postr',
      version=__version__,
      description='Flickr Uploader',
      author='Ross Burton',
      author_email='ross@burtonini.com',
      url='http://www.burtonini.com/',

      scripts=['postr'],
      package_dir={'postr': 'src'},
      packages=['postr'],
      package_data={'postr': ['postr.glade']},
      data_files=[('share/applications', ['data/postr.desktop']),
                  ('share/icons/hicolor/16x16/apps', glob('data/16x16/*.png')),
                  ('share/icons/hicolor/22x22/apps', glob('data/22x22/*.png')),
                  ('share/icons/hicolor/24x24/apps', glob('data/24x24/*.png')),
                  ('share/icons/hicolor/32x32/apps', glob('data/32x32/*.png')),
                  ('share/icons/hicolor/scalable/apps', glob('data/scalable/*.svg')),
                  ], cmdclass={'install_data': InstallData}

      )

# TODO: install translations
# TODO: update icon cache
# TODO: rewrite in autotools because this is getting silly

# Postr's Nautilus Extension, an extension to upload to Flickr using Postr
#
# Copyright (C) 2007 German Poo-Caaman~o <gpoo@gnome.org>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51 Franklin
# St, Fifth Floor, Boston, MA 02110-1301 USA

import nautilus
import os
import os.path
import gobject
from urllib import unquote

PROGRAM_NAME = 'postr'

class PostrExtension(nautilus.MenuProvider):
    def __init__(self):
        # The constructor must be exists, even if there is nothing
        # to initialize (See Bug #374958)
        #self.program = None
        pass
    
    def locate_program(self, program_name):
        path_list = os.environ['PATH']
        for d in path_list.split(os.path.pathsep):
            try:
                if program_name in os.listdir(d):
                    return os.path.sep.join([d, program_name])
            except OSError:
                # Normally is a bad idea use 'pass' in a exception,
                # but in this case we don't care if the directory
                # in path exists or not.
                pass

        return None

    def upload_files(self, menu, files):
        # This is the method invoked when our extension is activated
        # Do whatever you want to do with the files selected
        if len(files) == 0:
            return

        names = [ unquote(file.get_uri()[7:]) for file in files ]

        argv = [ PROGRAM_NAME ] + names

        # TODO: use startup notification
        gobject.spawn_async(argv, flags=gobject.SPAWN_SEARCH_PATH)

    def get_file_items(self, window, files):
        # Show the menu iif:
        # - There is at least on file selected
        # - All the selected files are images
        # - All selected images are locals (currently Postr doesn't have
        #   support for gnome-vfs
        # - Postr is installed (is in PATH)
        if len(files) == 0:
            return
        
        for file in files:
            if file.is_directory() or file.get_uri_scheme() != 'file':
                return
            if not file.is_mime_type("image/*"):
                return

        #self.program = self.locate_program(PROGRAM_NAME)
        #if not self.program:
        #    return

        item = nautilus.MenuItem('PostrExtension::upload_files',
                                 'Upload to Flickr...' ,
                                 'Upload the selected files into Flickr')
        item.connect('activate', self.upload_files, files)

        return item,

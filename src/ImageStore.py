# Postr, a Flickr Uploader
#
# Copyright (C) 2006-2008 Ross Burton <ross@burtonini.com>
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

import gobject, gtk

# Column indexes
(COL_FILENAME, # The filename of an image (can be None)
 COL_SIZE, # Integer, file size
 COL_IMAGE, # The image data (if filename is None)
 COL_PREVIEW, # A 512x512 preview of the image
 COL_THUMBNAIL, # A 64x64 thumbnail of the image
 COL_TITLE, # The image title
 COL_DESCRIPTION, # The image description
 COL_TAGS, # A space deliminated list of tags for the image
 COL_SET, # An iterator point to the set to put the photo in
 COL_GROUPS, # Pyton list of group IDs
 COL_PRIVACY, # Iterator containing privacy rules
 COL_SAFETY, # Iterator containing safety
 COL_VISIBLE, # If the image is searchable
 COL_CONTENT_TYPE, # Iterator containing content type
 ) = range (0, 14)

class ImageStore (gtk.ListStore):
    def __init__(self):
        gtk.ListStore.__init__(self, gobject.TYPE_STRING, # COL_FILENAME
                               gobject.TYPE_INT, # COL_SIZE
                               gtk.gdk.Pixbuf, # COL_IMAGE
                               gtk.gdk.Pixbuf, # COL_PREVIEW
                               gtk.gdk.Pixbuf,  #COL_THUMBNAIL
                               gobject.TYPE_STRING, # COL_TITLE
                               gobject.TYPE_STRING, # COL_DESCRIPTION
                               gobject.TYPE_STRING, # COL_TAGS
                               gtk.TreeIter, # COL_SET
                               object, # COL_GROUPS
                               gtk.TreeIter, # COL_PRIVACY
                               gtk.TreeIter, # COL_SAFETY
                               gobject.TYPE_BOOLEAN, # COL_VISIBLE
                               gtk.TreeIter) # COL_CONTENT_TYPE
        self._dirty = False
        self.connect("row-changed", self._on_row_changed)

    def dirty(self):
        return self._dirty

    def markClean(self):
        self._dirty = False

    def _on_row_changed(self, model, path, iter):
        self._dirty = self.iter_n_children(None) > 0

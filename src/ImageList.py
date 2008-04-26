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

import gtk
import pango 

import ImageStore

# Constants for the drag handling
(DRAG_URI,
 DRAG_IMAGE) = range (0, 2)

class ImageList(gtk.TreeView):
    def __init__(self):
        gtk.TreeView.__init__(self)

        column = gtk.TreeViewColumn('Preview', 
                                     gtk.CellRendererPixbuf(),
                                    pixbuf=ImageStore.COL_THUMBNAIL)

        self.append_column(column)

        renderer =  gtk.CellRendererText()
        renderer.set_property('ellipsize', pango.ELLIPSIZE_END) 

        column = gtk.TreeViewColumn('Info', renderer)
        column.set_cell_data_func(renderer, self.data_func)
        self.append_column(column)

        self.set_headers_visible(False)
        self.set_enable_search(False)

        selection = self.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)

        # Setup the drag and drop
        self.drag_dest_set (gtk.DEST_DEFAULT_ALL, (), gtk.gdk.ACTION_COPY)
        targets = self.drag_dest_get_target_list()
        targets = gtk.target_list_add_image_targets (targets, DRAG_IMAGE, False)
        targets = gtk.target_list_add_uri_targets (targets, DRAG_URI)
        self.drag_dest_set_target_list (targets)

    def data_func(self, column, cell, model, it):
        from xml.sax.saxutils import escape

        (title, description, tags) = model.get(it, ImageStore.COL_TITLE, ImageStore.COL_DESCRIPTION, ImageStore.COL_TAGS)
        
        if title:
            info_title = title
        else:
            info_title = _("No title")

        if description:
            # Clip the description because it could be long and have multiple lines
            # TODO: Clip at 20 characters, or the first line.
            info_desc = description[:20]
        else:
            info_desc = ""

        s = "<b><big>%s</big></b>\n%s\n" % (escape (info_title), escape (info_desc))
        if tags:
            colour = self.style.text[gtk.STATE_INSENSITIVE].pixel
            s = s + "<span color='#%X'>%s</span>" % (colour, escape (tags))
        
        cell.set_property("markup", s)


# Postr, a Flickr Uploader
#
# Copyright (C) 2008 Ross Burton <ross@burtonini.com>
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

import gobject, gtk, pango
from ErrorDialog import ErrorDialog
import util

(COL_SELECTED,
 COL_ID,
 COL_NAME,
 COL_ICON) = range(0, 4)

class GroupSelector(gtk.TreeView):

    __gsignals__ = {
        'changed' : (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
        }
    
    def __init__(self, flickr):
        self.flickr = flickr
        self.model = gtk.ListStore(gobject.TYPE_BOOLEAN,
                                   gobject.TYPE_STRING,
                                   gobject.TYPE_STRING,
                                   gtk.gdk.Pixbuf)
        self.model.connect("row-changed", lambda model, path, iter: self.emit("changed"))
        
        gtk.TreeView.__init__(self, self.model)
        
        column = gtk.TreeViewColumn('')
        column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.append_column(column)
        
        renderer =  gtk.CellRendererToggle()
        def toggled(r, path):
            self.model[path][COL_SELECTED] = not r.get_active()
        renderer.connect("toggled", toggled)
        column.pack_start(renderer, False)
        column.add_attribute(renderer, "active", COL_SELECTED)
        
        renderer =  gtk.CellRendererPixbuf()
        column.pack_start(renderer, False)
        column.add_attribute(renderer, "pixbuf", COL_ICON)
        
        renderer =  gtk.CellRendererText()
        column.pack_start(renderer, True)
        column.add_attribute(renderer, "text", COL_NAME)
        
        self.set_fixed_height_mode(True)
        self.set_headers_visible(False)
        self.set_search_column(COL_NAME)
        # TODO: enable case insensitive substring searching
    
    def update(self):
        # TODO: block changed signals
        self.flickr.groups_pools_getGroups().addCallbacks(self.got_groups, self.twisted_error)
    
    def got_groups(self, rsp):
        from elementtree.ElementTree import dump
        for group in rsp.findall("groups/group"):
            it = self.model.append()
            self.model.set (it,
                            COL_ID, group.get("id"),
                            COL_NAME, group.get("name"))
            def got_thumb(thumb, it):
                self.model.set (it, COL_ICON, thumb)
            util.get_buddyicon(self.flickr, group, 24).addCallback(got_thumb, it)
    
    def twisted_error(self, failure):
        dialog = ErrorDialog(self.window)
        dialog.set_from_failure(failure)
        dialog.show_all()

    def get_selected_groups(self):
        return [row[COL_ID] for row in self.model if row[COL_SELECTED]]

    def set_selected_groups(self, groups):
        # Handle groups being None */
        if groups is None: groups = ()
        for row in self.model:
            row[COL_SELECTED] = row[COL_ID] in groups

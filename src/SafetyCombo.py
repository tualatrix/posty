# Postr, a Flickr Uploader
#
# Copyright (C) 2006-2007 Ross Burton <ross@burtonini.com>
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

class SafetyCombo(gtk.ComboBox):
    def __init__(self):
        gtk.ComboBox.__init__(self)
        # Name, is_public, is_family, is_friend
        model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_INT)
        model.set(model.append(), 0, "Safe", 1, 1)
        model.set(model.append(), 0, "Moderate", 1, 2)
        model.set(model.append(), 0, "Restricted", 1, 3)
        self.model = model
        self.set_model(model)
        self.set_active(0)

        cell = gtk.CellRendererText()
        self.pack_start(cell)
        self.add_attribute(cell, "text", 0)

    def get_safety_for_iter(self, it):
        if it is None: return None
        return self.model.get_value(it, 1)

    def get_active_safety(self):
        return self.get_safety_for_iter(self.get_active_iter())

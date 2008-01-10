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

class PrivacyCombo(gtk.ComboBox):
    def __init__(self):
        gtk.ComboBox.__init__(self)
        # Name, is_public, is_family, is_friend
        model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_BOOLEAN, gobject.TYPE_BOOLEAN, gobject.TYPE_BOOLEAN)
        model.set(model.append(), 0, "Public", 1, True, 2, False, 3, False)
        model.set(model.append(), 0, "Family Only", 1, False, 2, True, 3, False)
        model.set(model.append(), 0, "Friends and Family Only", 1, False, 2, True, 3, True)
        model.set(model.append(), 0, "Private", 1, False, 2, False, 3, False)
        self.model = model
        self.set_model(model)
        self.set_active(0)

        cell = gtk.CellRendererText()
        self.pack_start(cell)
        self.add_attribute(cell, "text", 0)

    # (is_public, is_family, is_friend)
    def get_active_acls(self):
        return self.get_acls_for_iter(self.get_active_iter())

    # (is_public, is_family, is_friend)
    def get_acls_for_iter(self, it):
        if it is None: return None
        return self.model.get(it, 1, 2, 3)

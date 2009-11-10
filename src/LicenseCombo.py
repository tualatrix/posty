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

class LicenseCombo(gtk.ComboBox):
    def __init__(self, flickr):
        gtk.ComboBox.__init__(self)
        self.flickr = flickr
        
        self.model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_INT)
        #self.model.set(self.model.append(), 0, "All rights reserved", 1, 0)
        self.set_model(self.model)
        self.set_active(-1)

        cell = gtk.CellRendererText()
        self.pack_start(cell)
        self.add_attribute(cell, "text", 0)

    def twisted_error(self, failure):
        from ErrorDialog import ErrorDialog
        dialog = ErrorDialog()
        dialog.set_from_failure(failure)
        dialog.show_all()

    def __got_licenses(self, rsp):
        """Callback for the photos.licenses.getInfo call"""
        for license in rsp.findall("licenses/license"):
            license_id = int(license.get("id"))
            it = self.model.append()
            self.model.set(it,
                           0, license.get("name"),
                           1, license_id)
            # Set default license to All Rights Reserved.
            # I haven't found a way to get the default license
            # from flickr by the API.
            if license_id == 0:
                self.set_active_iter(it)

    def update(self):
        self.flickr.photos_licenses_getInfo().addCallbacks(self.__got_licenses,
                                                           self.twisted_error)

    def get_license_for_iter(self, it):
        if it is None: return None
        return self.model.get_value(it, 1)

    def get_active_license(self):
        return self.get_license_for_iter(self.get_active_iter())

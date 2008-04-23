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
from twisted.web.client import getPage

class SetCombo(gtk.ComboBox):
    def __init__(self, flickr):
        gtk.ComboBox.__init__(self)
        self.flickr = flickr
        
        # ID, name, thumbnail
        self.model =  gtk.ListStore (gobject.TYPE_STRING, gobject.TYPE_STRING, gtk.gdk.Pixbuf)
        self.model.set (self.model.append(), 0, None, 1, "None")

        self.set_model(self.model)
        self.set_active (-1)

        renderer = gtk.CellRendererPixbuf()
        self.pack_start (renderer, expand=False)
        self.set_attributes(renderer, pixbuf=2)
        renderer = gtk.CellRendererText()
        self.pack_start (renderer, expand=False)
        self.set_attributes(renderer, text=1)

    def twisted_error(self, failure):
        from ErrorDialog import ErrorDialog
        dialog = ErrorDialog(self.window)
        dialog.set_from_failure(failure)
        dialog.show_all()

    def __got_set_thumb(self, page, it):
        loader = gtk.gdk.PixbufLoader()
        loader.set_size (32, 32)
        loader.write(page)
        loader.close()
        self.model.set (it, 2, loader.get_pixbuf())
    
    def __got_photosets(self, rsp):
        """Callback for the photosets.getList call"""
        for photoset in rsp.findall("photosets/photoset"):
            it = self.model.append()
            self.model.set (it,
                           0, photoset.get("id"),
                           1, photoset.find("title").text)

            url = "http://static.flickr.com/%s/%s_%s%s.jpg" % (photoset.get("server"), photoset.get("primary"), photoset.get("secret"), "_s")
            getPage (url).addCallback (self.__got_set_thumb, it).addErrback(self.twisted_error)

    def update(self):
        self.flickr.photosets_getList().addCallback(self.__got_photosets), self.twisted_error)

    def get_id_for_iter(self, it):
        if it is None: return None
        return self.model.get(it, 0)

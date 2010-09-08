#s Postr, a Flickr Uploader
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

import datetime
import gobject, gtk
from twisted.web.client import getPage

_NO_PHOTOSET_ID = "-1"
_NO_PHOTOSET_LABEL = _("None")
_DEFAULT_NEW_PHOTOSET_LABEL = _("Create Photoset \"%s\"")
_DEFAULT_NEW_PHOTOSET_NAME = datetime.datetime.strftime(datetime.datetime.today(),
                                                        _("new photoset (%m-%d-%y)"))

# Column Indexes
( COL_SETID,
  COL_SETLABEL,
  COL_THUMBNAIL ) = range(0, 3)

class SetCombo(gtk.ComboBox):
    def __init__(self, flickr):
        gtk.ComboBox.__init__(self)
        self.flickr = flickr
        
        # Calculate the size of thumbnails based on the size of the text
        # renderer, but provide a default in case style-set isn't called.
        self.connect("style-set", self.style_set)
        self.thumb_size = 24

        # ID, name, thumbnail
        self.model =  gtk.ListStore (gobject.TYPE_STRING, gobject.TYPE_STRING, gtk.gdk.Pixbuf)
        self.model.set (self.model.append(),
                        COL_SETID, None,
                        COL_SETLABEL, _NO_PHOTOSET_LABEL)
        self._create_new_photoset_iter()

        self.set_model(self.model)
        self.set_active (-1)

        renderer = gtk.CellRendererPixbuf()
        self.pack_start (renderer, expand=False)
        self.set_attributes(renderer, pixbuf=COL_THUMBNAIL)
        
        self.text_renderer = gtk.CellRendererText()
        self.pack_start (self.text_renderer, expand=False)
        self.set_attributes(self.text_renderer, text=COL_SETLABEL)

    def style_set(self, widget, old_style):
        self.thumb_size = self.text_renderer.get_size(self, None)[3]
    
    def twisted_error(self, failure):
        from ErrorDialog import ErrorDialog
        dialog = ErrorDialog()
        dialog.set_from_failure(failure)
        dialog.show_all()

    def __got_set_thumb(self, page, it):
        loader = gtk.gdk.PixbufLoader()
        loader.set_size (self.thumb_size, self.thumb_size)
        loader.write(page)
        loader.close()
        self.model.set (it, COL_THUMBNAIL, loader.get_pixbuf())
    
    def __got_albums(self, rsp):
        """Callback for the albums.getList call"""
        for photoset in rsp.findall("albums/photoset"):
            it = self.model.append()
            self.model.set (it,
                           0, photoset.get("id"),
                           1, photoset.find("title").text)

            url = "http://static.flickr.com/%s/%s_%s%s.jpg" % (photoset.get("server"), photoset.get("primary"), photoset.get("secret"), "_s")
            getPage (url).addCallback(self.__got_set_thumb, it).addErrback(self.twisted_error)

    def update(self):
        self.flickr.albums_getList().addCallbacks(self.__got_albums, self.twisted_error)

    def get_id_for_iter(self, it):
        if it is None: return None
        return self.model.get(it, COL_SETID)

    # This is needed for imports to behave correctly.  The
    #   index of the iterator on export might no longer be valid
    #   when the upload set is imported.
    def get_iter_for_set(self, set_id):
        iter = self.model.get_iter_root()
        while iter:
            iter_set_id = self.model.get(iter, COL_SETID)
            if iter_set_id[0] == set_id:
                return iter
            iter = self.model.iter_next(iter)
        return None

    def _get_new_photoset_iter(self):
        return self.model.get_iter(1)

    def _create_new_photoset_iter(self):
        self.model.set(self.model.insert(1))
        self.update_new_photoset("", id=_NO_PHOTOSET_ID)

    def update_new_photoset(self, new_photoset_name, id=None):
        self.new_photoset_name = new_photoset_name \
            if new_photoset_name else _DEFAULT_NEW_PHOTOSET_NAME
        new_set_label = _DEFAULT_NEW_PHOTOSET_LABEL % self.new_photoset_name
        it = self._get_new_photoset_iter()
        if id is not None:
            self.model.set_value(it, COL_SETID, id)
        self.model.set_value(it, COL_SETLABEL, new_set_label)

    def _response_to_dialog(self, entry, dialog, response):
        dialog.response(response)

    def name_new_photoset(self):
        dialog = gtk.MessageDialog(None,
                                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_QUESTION,
                                   gtk.BUTTONS_OK_CANCEL,
                                   None)
        dialog.set_markup(_("Name for the new photoset:"))
        entry = gtk.Entry()
        entry.set_text(self.new_photoset_name)
        # so that you can press 'enter' to close dialog
        entry.connect("activate", self._response_to_dialog, dialog, gtk.RESPONSE_OK)
        dialog.vbox.pack_end(entry, True, True, 0)
        dialog.show_all()

        response = dialog.run()
        dialog.destroy()
        if response == gtk.RESPONSE_OK:
            text = entry.get_text()
            self.update_new_photoset(text.strip())
        return self.new_photoset_name

    def set_recently_created_photoset(self, photoset_name, photoset_id):
        if photoset_name == self.new_photoset_name and photoset_id:
            self.update_new_photoset(photoset_name, id=photoset_id)
            self._create_new_photoset_iter()

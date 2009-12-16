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

class ProgressDialog(gtk.Dialog):
    def __init__(self, cancel_cb):
        gtk.Dialog.__init__(self, title="", flags=gtk.DIALOG_NO_SEPARATOR)
        self.cancel_cb = cancel_cb
        
        self.set_resizable(False)
        self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
        self.connect("response", self.on_response)
        
        vbox = gtk.VBox(False, 8)
        vbox.set_border_width(8)
        self.vbox.add(vbox)
        
        hbox = gtk.HBox(False, 8)
        vbox.add (hbox)

        self.thumbnail = gtk.Image()
        hbox.pack_start (self.thumbnail, False, False, 0)

        self.label = gtk.Label()
        self.label.set_alignment (0.0, 0.0)
        hbox.pack_start (self.label, True, True, 0)
        
        self.image_progress = gtk.ProgressBar()
        vbox.add(self.image_progress)

        vbox.show_all()

    def on_response(self, dialog, response):
        if response == gtk.RESPONSE_CANCEL or response == gtk.RESPONSE_DELETE_EVENT:
            self.cancel_cb()
    
if __name__ == "__main__":
    import gobject
    d = ProgressDialog()
    d.thumbnail.set_from_icon_name ("stock_internet", gtk.ICON_SIZE_DIALOG)
    d.label.set_text(_("Uploading"))
    def pulse():
        d.image_progress.pulse()
        return True
    gobject.timeout_add(200, pulse)
    d.show()
    gtk.main()

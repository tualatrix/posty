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
from ErrorDialog import ErrorDialog
from util import greek
from xml.sax.saxutils import escape

class StatusBar(gtk.Label):
    def __init__(self, flickr):
        gtk.Label.__init__(self)
        self.set_alignment(0.0, 0.5)
        self.flickr = flickr
        self.quota = None
        self.to_upload = None

    def __update(self):
        message = ""

        if self.flickr.get_username():
            message = message + _("Logged in as <b>%s</b>.  ") % escape(self.flickr.get_fullname() or self.flickr.get_username())
        
        if self.quota and self.to_upload:
            message = message + _("You can upload %(quota)s this month, and have %(to_upload)s to upload.") % self.__dict__
        elif self.quota:
            message = message + _("You can upload %(quota)s this month.") % self.__dict__
        elif self.to_upload:
            message = message + _("%(to_upload)s to upload.") % self.__dict__

        self.set_markup(message)
    
    def update_quota(self):
        """Call Flickr to get the current upload quota, and update the status bar."""
        def got_quota(rsp):
            if int(rsp.find("user").get("ispro")):
                self.quota = None
            else:
                self.quota = greek(int(rsp.find("user/bandwidth").get("remainingbytes")))
            self.__update()
        def error(failure):
            dialog = ErrorDialog(self.get_toplevel())
            dialog.set_from_failure(failure)
            dialog.show_all()
        self.flickr.people_getUploadStatus().addCallbacks(got_quota, error)

    def set_upload(self, to_upload):
        """Set the amount of data to be uploaded, and update the status bar."""
        if to_upload:
            self.to_upload = greek(to_upload)
        else:
            self.to_upload = None
        self.__update()

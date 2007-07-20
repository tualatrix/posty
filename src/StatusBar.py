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

import gtk
from util import greek

class StatusBar(gtk.Statusbar):
    def __init__(self, flickr):
        gtk.Statusbar.__init__(self)
        self.context = self.get_context_id("quota")
        self.flickr = flickr
        self.quota = None
        self.to_upload = 0

    def __update(self):
        self.pop(self.context)
        if self.quota and self.to_upload:
            message = _("You have %(quota)s remaining this month (%(to_upload)s to upload)") % self.__dict__
        elif self.quota:
            message = _("You have %(quota)s remaining this month") % self.__dict__
        else:
            message = _("%(to_upload)s to upload") % self.__dict__
        self.push(self.context, message)
    
    def update_quota(self):
        def got_quota(rsp):
            self.quota = greek(int(rsp.find("user/bandwidth").get("remainingbytes")))
            self.__update
        # TODO: error handler
        self.flickr.people_getUploadStatus().addCallback(got_quota)

    def set_upload(self, to_upload):
        self.to_upload = greek(to_upload)
        self.__update()

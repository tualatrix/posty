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

import subprocess
import gtk, gconf

def on_url_clicked(button, url):
    """Global LinkButton handler that starts the default GNOME HTTP handler, or
    firefox."""
    client = gconf.client_get_default()
    browser = client.get_string("/desktop/gnome/url-handlers/http/command") or "firefox %s"
    # Because URLs contain & it needs to be quoted
    browser = browser % '"' + url + '"'
    subprocess.Popen(args=browser, shell=True)
    # TODO: if that didn't work fallback on x-www-browser or something

class AuthenticationDialog(gtk.Dialog):
    def __init__(self, parent, url):
        gtk.Dialog.__init__(self,
                            title=_("Flickr Uploader"), parent=parent,
                            flags=gtk.DIALOG_NO_SEPARATOR,
                            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                                     _("Continue"), gtk.RESPONSE_ACCEPT))
        vbox = gtk.VBox(spacing=8)
        vbox.set_border_width(8)
        
        label = gtk.Label(_("Postr needs to login to Flickr to upload your photos. "
                          "Please click on the link below to login to Flickr."))
        label.set_line_wrap(True)
        vbox.add(label)

        # gtk.LinkButton is only in 2.10, so use a normal button if it isn't
        # available.
        if hasattr(gtk, "LinkButton"):
            gtk.link_button_set_uri_hook(on_url_clicked)
            button = gtk.LinkButton(url, _("Login to Flickr"))
        else:
            button = gtk.Button(_("Login to Flickr"))
            button.connect("clicked", on_url_clicked, url)
        vbox.add(button)
        
        self.vbox.add(vbox)
        self.show_all()

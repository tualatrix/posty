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

import gtk, os

def greek(size):
    """Take a quantity (like 1873627) and display it in a human-readable rounded
    form (like 1.8M)"""
    _abbrevs = [
        (1<<50L, 'P'),
        (1<<40L, 'T'), 
        (1<<30L, 'G'), 
        (1<<20L, 'M'), 
        (1<<10L, 'k'),
        (1, '')
        ]
    for factor, suffix in _abbrevs:
        if size > factor:
            break
    return "%.1f%s" % (float(size)/factor, suffix)


def get_widget_checked(glade, name):
    """Get widget name from glade, and if it doesn't exist raise an exception
    instead of returning None."""
    widget = glade.get_widget(name)
    if widget is None: raise "Cannot find widget %s" % name
    return widget

def get_glade_widgets (glade, object, widget_names):
    """Get the widgets in the list widget_names from the GladeXML object glade
    and set them as attributes on object."""
    for name in widget_names:
        setattr(object, name, get_widget_checked(glade, name))


def get_thumb_size(srcw, srch, dstw, dsth):
    """Scale scrw x srch to an dimensions with the same ratio that fits as
    closely as possible to dstw x dsth."""
    scalew = dstw/float(srcw)
    scaleh = dsth/float(srch)
    scale = min(scalew, scaleh)
    return (int(srcw * scale), int(srch * scale))

def align_labels(glade, names):
    """Add the list of widgets identified by names in glade to a horizontal
    sizegroup."""
    group = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)
    widget = [group.add_widget(get_widget_checked(glade, name)) for name in names]

def get_buddyicon(flickr, data):
    from twisted.web.client import getPage
    
    def got_thumb(page):
        loader = gtk.gdk.PixbufLoader()
        # TODO: parameterise this I guess
        loader.set_size (32, 32)
        loader.write(page)
        loader.close()
        return loader.get_pixbuf()
    
    if int(data.get("iconfarm")) > 0:
        url = "http://farm%s.static.flickr.com/%s/buddyicons/%s.jpg" % (data.get("iconfarm"), data.get("iconserver"), data.get("nsid"))
    else:
        url = "http://www.flickr.com/images/buddyicon.jpg"
    # TODO: cache the loaded images and return images from the cache
    return getPage(url).addCallback(got_thumb)

def get_cache_path():
    return os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache/"))

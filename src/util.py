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


def get_glade_widgets (glade, object, widget_names):
    """Get the widgets in the list widget_names from the GladeXML object glade
    and set them as attributes on object."""
    for name in widget_names:
        widget = glade.get_widget(name)
        if widget is None: raise "Cannot find widget %s" % name
        setattr(object, name, widget)


def get_thumb_size(srcw, srch, dstw, dsth):
    """Scale scrw x srch to an dimensions with the same ratio that fits as
    closely as possible to dstw x dsth."""
    scalew = dstw/float(srcw)
    scaleh = dsth/float(srch)
    scale = min(scalew, scaleh)
    return (int(srcw * scale), int(srch * scale))

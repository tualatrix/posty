#! /usr/bin/python

# Postr, a Flickr Uploader
#
# Copyright (C) 2006 Ross Burton <ross@burtonini.com>
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

import os, threading
from urlparse import urlparse

import pygtk; pygtk.require ("2.0")
import gobject, gtk, gtk.glade
gtk.gdk.threads_init()

import EXIF
from flickrapi import FlickrAPI

# My top secret Flickr API keys
flickrAPIKey = "c53cebd15ed936073134cec858036f1d"
flickrSecret = "7db1b8ef68979779"

fapi = FlickrAPI(flickrAPIKey, flickrSecret)
# TODO: do this in a thread or something to stop blocking
token = fapi.getToken(browser="epiphany -p", perms="write")

# Constants for the drag handling
(DRAG_URI,
 DRAG_IMAGE) = range (0, 2)

# Column indexes
(COL_URI,
 COL_THUMBNAIL,
 COL_TITLE,
 COL_DESCRIPTION,
 COL_TAGS) = range (0, 5)
model = gtk.ListStore (gobject.TYPE_STRING, gtk.gdk.Pixbuf, gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_STRING)
current_it = None

glade = gtk.glade.XML(os.path.join (os.path.dirname(__file__), "postr.glade"))
# TODO: autoconnect

window = glade.get_widget("main_window")

# TODO: hook into state of upload and confirm quit if still uploading
window.connect('destroy', gtk.main_quit)
glade.get_widget('quit').connect('activate', gtk.main_quit)

thumbnail_image = glade.get_widget('thumbnail_image')
title_entry = glade.get_widget("title_entry")
desc_entry = glade.get_widget("desc_entry")
tags_entry = glade.get_widget("tags_entry")

def on_field_changed(entry, column):
    global current_it
    # We often get called when there is no iterator as we've just cleared the
    # field
    if current_it is None: return
    model.set_value (current_it, column, entry.get_text())
title_entry.connect('changed', on_field_changed, COL_TITLE)
desc_entry.connect('changed', on_field_changed, COL_DESCRIPTION)
tags_entry.connect('changed', on_field_changed, COL_TAGS)

iconview = glade.get_widget("iconview")
iconview.set_model (model)
iconview.set_text_column (COL_TITLE)
iconview.set_pixbuf_column (COL_THUMBNAIL)

iconview.drag_dest_set (gtk.DEST_DEFAULT_ALL, (), gtk.gdk.ACTION_COPY)
targets = gtk.target_list_add_uri_targets(None, DRAG_URI)
targets = gtk.target_list_add_image_targets(targets, DRAG_IMAGE, False)
iconview.drag_dest_set_target_list(targets)

def on_selection_changed(iconview):
    global current_it
    
    items = iconview.get_selected_items()
    if len(items) > 1:
        print "Unexpected number of selections"
        return
    
    if items:
        current_it = model.get_iter(items[0])
        (title, desc, tags, thumb) = model.get(current_it,
                                               COL_TITLE,
                                               COL_DESCRIPTION,
                                               COL_TAGS,
                                               COL_THUMBNAIL)
        
        title_entry.set_sensitive(True)
        title_entry.set_text(title)
        desc_entry.set_sensitive(True)
        desc_entry.set_text(desc)
        tags_entry.set_sensitive(True)
        tags_entry.set_text(tags)

        thumbnail_image.set_from_pixbuf(thumb)
    else:
        current_it = None
        title_entry.set_sensitive(False)
        title_entry.set_text("")
        desc_entry.set_sensitive(False)
        desc_entry.set_text("")
        tags_entry.set_sensitive(False)
        tags_entry.set_text("")
        
        thumbnail_image.set_from_pixbuf(None)

iconview.connect('selection-changed', on_selection_changed)

def on_drag_uri(widget, context, x, y, selection, targetType, timestamp):
    if targetType == DRAG_URI:
        for uri in selection.get_uris():
            
            # TODO: MIME type check
            
            # TODO: use gnome-vfs to handle remote files
            filename = urlparse(uri)[2]

            exif = EXIF.process_file(open(filename, 'rb'))

            thumb = exif.get('JPEGThumbnail', None)
            if thumb:
                loader = gtk.gdk.PixbufLoader()
                def on_size_prepared(loader, width, height):
                    ratio = width/float(height)
                    if width > height:
                        loader.set_size(64, int(64/ratio))
                    else:
                        loader.set_size(int(64/ratio), 64)
                loader.connect('size-prepared', on_size_prepared)
                loader.write(thumb)
                loader.close()
                thumb = loader.get_pixbuf()
                # TODO: rotate if required?
            else:
                thumb = gtk.gdk.pixbuf_new_from_file_at_size (filename, 64, 64)

            # Extra useful data from image
            title = os.path.splitext(os.path.basename(filename))[0] # TODO: more
            desc = exif.get('Image ImageDescription', "")
            
            model.set(model.append(),
                      COL_URI, uri,
                      COL_THUMBNAIL, thumb,
                      COL_TITLE, title,
                      COL_DESCRIPTION, desc,
                      COL_TAGS, "")
    elif targetType == DRAG_IMAGE:
        print "TODO"
    else:
        print "Unhandled target type %d" % targetType
    
    context.finish(True, True, timestamp)

iconview.connect('drag-data-received', on_drag_uri)

class UploadTask:
    uri = None
    title = None
    description = None
    tags = None
    
from Queue import Queue
upload_queue = Queue()

# Called when the uploading is done, to empty the model and unlock the view.
def done():
    gtk.gdk.threads_enter()
    model.clear()
    iconview.set_sensitive(True)
    # TODO: enable upload menu item
    gtk.gdk.threads_leave()

class Uploader(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        
    def run(self):
        while 1:
            # This blocks when the queue is empty
            t = upload_queue.get()
            ret = fapi.upload(api_key=flickrAPIKey, auth_token=token,
                              filename=urlparse(t.uri)[2],
                              title=t.title, description=t.description, tags=t.tags)
            if fapi.getRspErrorCode(ret) != 0:
                # TODO: fire error dialog
                print fapi.getPrintableError(rsp)

            if upload_queue.empty():
                done()

def on_upload_activate(menuitem):
    it = model.get_iter_first()
    # If we have some pictures, disable the iconview
    if it is not None:
        # TODO: disable upload menu item
        iconview.set_sensitive(False)
    
    while it is not None:
        (uri, title, desc, tags) = model.get(it, COL_URI, COL_TITLE, COL_DESCRIPTION, COL_TAGS)

        t = UploadTask()
        t.uri = uri
        t.title = title
        t.description = desc
        t.tags = tags

        upload_queue.put(t)
        
        it = model.iter_next(it)

glade.get_widget('upload').connect('activate', on_upload_activate)

def on_about_activate(menuitem):
    dialog = gtk.AboutDialog()
    dialog.set_transient_for(window)
    dialog.set_name('Flickr Uploader')
    dialog.set_copyright(u'Copyright \u00A9 2006 Ross Burton')
    dialog.set_authors(('Ross Burton <ross@burtonini.com>',))
    dialog.set_website('http://burtonini.com/')
    dialog.run()
    dialog.destroy()

glade.get_widget('about').connect('activate', on_about_activate)

Uploader().start()
window.show()
gtk.main()

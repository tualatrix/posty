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
from Queue import Queue
from urlparse import urlparse

import pygtk; pygtk.require ("2.0")
import gobject, gtk, gtk.glade
gtk.gdk.threads_init()

import EXIF
from flickrapi import FlickrAPI

# My top secret Flickr API keys
flickrAPIKey = "c53cebd15ed936073134cec858036f1d"
flickrSecret = "7db1b8ef68979779"

# TODO: do this in a thread or something to stop blocking
fapi = FlickrAPI(flickrAPIKey, flickrSecret)
token = fapi.getToken(browser="epiphany -p", perms="write")

# Constants for the drag handling
(DRAG_URI,
 DRAG_IMAGE) = range (0, 2)

# Column indexes
(COL_URI,
 COL_IMAGE,
 COL_THUMBNAIL,
 COL_TITLE,
 COL_DESCRIPTION,
 COL_TAGS) = range (0, 6)


# The task queue to transfer jobs to the upload thread
upload_queue = Queue()
uploading = threading.Event()

class AboutDialog(gtk.AboutDialog):
    def __init__(self, parent):
        gtk.AboutDialog.__init__(self)
        self.set_transient_for(parent)
        self.set_name('Flickr Uploader')
        self.set_copyright(u'Copyright \u00A9 2006 Ross Burton')
        self.set_authors(('Ross Burton <ross@burtonini.com>',))
        self.set_website('http://burtonini.com/')


class Postr:
    def __init__(self):
        glade = gtk.glade.XML(os.path.join (os.path.dirname(__file__), "postr.glade"))
        glade.signal_autoconnect(self)

        self.window = glade.get_widget("main_window")

        self.thumbnail_image = glade.get_widget('thumbnail_image')
        self.title_entry = glade.get_widget("title_entry")
        self.desc_entry = glade.get_widget("desc_entry")
        self.tags_entry = glade.get_widget("tags_entry")

        self.model = gtk.ListStore (gobject.TYPE_STRING,
                                    gtk.gdk.Pixbuf,
                                    gtk.gdk.Pixbuf,
                                    gobject.TYPE_STRING,
                                    gobject.TYPE_STRING,
                                    gobject.TYPE_STRING)
        self.current_it = None

        self.title_entry.connect('changed', self.on_field_changed, COL_TITLE)
        self.desc_entry.connect('changed', self.on_field_changed, COL_DESCRIPTION)
        self.tags_entry.connect('changed', self.on_field_changed, COL_TAGS)

        self.iconview = glade.get_widget("iconview")
        self.iconview.set_model (self.model)
        self.iconview.set_text_column (COL_TITLE)
        self.iconview.set_pixbuf_column (COL_THUMBNAIL)
    
        self.iconview.drag_dest_set (gtk.DEST_DEFAULT_ALL, (), gtk.gdk.ACTION_COPY)
        targets = ()
        targets = gtk.target_list_add_image_targets(targets, DRAG_IMAGE, False)
        targets = gtk.target_list_add_uri_targets(targets, DRAG_URI)
        self.iconview.drag_dest_set_target_list(targets)

    def on_field_changed(self, entry, column):
        items = self.iconview.get_selected_items()
        for path in items:
            it = self.model.get_iter(path)
            self.model.set_value (it, column, entry.get_text())
    
    def on_quit_activate (self, menuitem):
        if uploading.isSet():
            # TODO: if there are pending uploads, confirm first
            print "Uploading, should query user"
        gtk.main_quit()
    
    def on_about_activate(self, menuitem):
        dialog = AboutDialog(self.window)
        dialog.run()
        dialog.destroy()
    
    def on_upload_activate(self, menuitem):
        it = self.model.get_iter_first()
        # If we have some pictures, disable the iconview
        if it is not None:
            # TODO: disable upload menu item
            self.iconview.set_sensitive(False)
        
        while it is not None:
            (uri, pixbuf, title, desc, tags) = self.model.get(it,
                                                              COL_URI,
                                                              COL_IMAGE,
                                                              COL_TITLE,
                                                              COL_DESCRIPTION,
                                                              COL_TAGS)
    
            t = UploadTask()
            t.uri = uri
            t.pixbuf = pixbuf
            t.title = title
            t.description = desc
            t.tags = tags
    
            upload_queue.put(t)
            
            it = self.model.iter_next(it)
    
    def on_selection_changed(self, iconview):
        items = iconview.get_selected_items()

        def enable_field(field, text):
            field.set_sensitive(True)
            field.set_text(text)
        def disable_field(field):
            field.set_sensitive(False)
            field.set_text("")
        
        if items:
            # TODO: do something clever with multiple selections
            self.current_it = self.model.get_iter(items[0])
            (title, desc, tags, thumb) = self.model.get(self.current_it,
                                                        COL_TITLE,
                                                        COL_DESCRIPTION,
                                                        COL_TAGS,
                                                        COL_THUMBNAIL)
            
            enable_field(self.title_entry, title)
            enable_field(self.desc_entry, desc)
            enable_field(self.tags_entry, tags)
    
            self.thumbnail_image.set_from_pixbuf(thumb)
        else:
            self.current_it = None
            disable_field(self.title_entry)
            disable_field(self.desc_entry)
            disable_field(self.tags_entry)
            
            self.thumbnail_image.set_from_pixbuf(None)

    @staticmethod
    def get_thumb_size(width, height):
        ratio = width/float(height)
        if width > height:
            return (64, int(64/ratio))
        else:
            return (int(64/ratio), 64)
    
    def on_drag_data_received(self, widget, context, x, y, selection, targetType, timestamp):
        if targetType == DRAG_IMAGE:
            pixbuf = selection.get_pixbuf()
            sizes = self.get_thumb_size (pixbuf.get_width(), pixbuf.get_height())
            thumb = pixbuf.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)
            self.model.set(self.model.append(),
                           COL_IMAGE, pixbuf,
                           COL_URI, None,
                           COL_THUMBNAIL, thumb,
                           COL_TITLE, "",
                           COL_DESCRIPTION, "",
                           COL_TAGS, "")
        
        elif targetType == DRAG_URI:
            for uri in selection.get_uris():
                
                # TODO: MIME type check
                
                # TODO: use gnome-vfs to handle remote files
                filename = urlparse(uri)[2]
    
                exif = EXIF.process_file(open(filename, 'rb'))
    
                thumb = exif.get('JPEGThumbnail', None)
                if thumb:
                    loader = gtk.gdk.PixbufLoader()
                    def on_size_prepared(loader, width, height):
                        loader.set_size(*self.get_thumb_size(width, height))
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
                
                self.model.set(self.model.append(),
                               COL_URI, uri,
                               COL_IMAGE, None,
                               COL_THUMBNAIL, thumb,
                               COL_TITLE, title,
                               COL_DESCRIPTION, desc,
                               COL_TAGS, "")
        else:
            print "Unhandled target type %d" % targetType
        
        context.finish(True, True, timestamp)

    def done(self):
        gtk.gdk.threads_enter()
        self.model.clear()
        self.iconview.set_sensitive(True)
        # TODO: enable upload menu item
        gtk.gdk.threads_leave()


class UploadTask:
    uri = None
    pixbuf = None
    title = None
    description = None
    tags = None


class Uploader(threading.Thread):
    def __init__(self, postr):
        threading.Thread.__init__(self)
        self.setDaemon(True)
        self.postr = postr
        
    def run(self):
        while 1:
            # This blocks when the queue is empty
            t = upload_queue.get()
            uploading.set()
            
            # TODO: construct a list and pass that to avoid duplication
            if t.uri:
                ret = fapi.upload(api_key=flickrAPIKey, auth_token=token,
                                  filename=urlparse(t.uri)[2],
                                  title=t.title, description=t.description, tags=t.tags)
            elif t.pixbuf:
                # This isn't very nice, but might be the best way
                data = []
                t.pixbuf.save_to_callback(lambda d: data.append(d), "png", {})
                ret = fapi.upload(api_key=flickrAPIKey, auth_token=token,
                                  imageData=''.join(data),
                                  title=t.title, description=t.description, tags=t.tags)
            else:
                print "No data in task"
                continue
            
            if fapi.getRspErrorCode(ret) != 0:
                # TODO: fire error dialog
                print fapi.getPrintableError(rsp)

            if upload_queue.empty():
                uploading.clear()
                self.postr.done()



if __name__ == "__main__":
    p = Postr()
    Uploader(p).start()
    p.window.show()
    gtk.main()

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

import gettext, logging, os
from urlparse import urlparse
from os.path import basename

import pygtk; pygtk.require ("2.0")
import gobject, gtk, gtk.glade

from AboutDialog import AboutDialog
from AuthenticationDialog import AuthenticationDialog

from flickrest import Flickr
import EXIF
import iptc as IPTC
from util import *


try:
    import gtkunique
    UniqueApp = gtkunique.UniqueApp
except ImportError:
    class UniqueApp:
        """A dummy UniqueApp for when gtkunique isn't installed."""
        def __init__(self, name):
            pass
        def add_window(self, window):
            pass
        def is_running(self):
            return False

#logging.basicConfig(level=logging.DEBUG)

# TODO: write a global error handler for passing to flickr methods that displays
# a dialog

# Constants for the drag handling
(DRAG_URI,
 DRAG_IMAGE) = range (0, 2)

# Column indexes
(COL_FILENAME, # The filename of an image (can be None)
 COL_IMAGE, # The image data (if filename is None)
 COL_PREVIEW, # A 512x512 preview of the image
 COL_THUMBNAIL, # A 64x64 thumbnail of the image
 COL_TITLE, # The image title
 COL_DESCRIPTION, # The image description
 COL_TAGS # A space deliminated list of tags for the image
 ) = range (0, 7)

# Exif information about image orientation
(ROTATED_180,
 ROTATED_90_CW,
 ROTATED_90_CCW
 ) = (3, 6, 8)


class Postr (UniqueApp):
    def __init__(self):
        UniqueApp.__init__(self, 'com.burtonini.Postr')
        try:
            self.connect("message", self.on_message)
        except AttributeError:
            pass
        
        self.flickr = Flickr(api_key="c53cebd15ed936073134cec858036f1d",
                             secret="7db1b8ef68979779",
                             perms="write")
        
        glade = gtk.glade.XML(os.path.join (os.path.dirname(__file__), "postr.glade"))
        glade.signal_autoconnect(self)

        get_glade_widgets (glade, self,
                           ("window",
                            "upload_menu",
                            "statusbar",
                            "thumbnail_image",
                            "title_entry",
                            "desc_entry",
                            "tags_entry",
                            "iconview",
                            "progress_dialog",
                            "progressbar",
                            "progress_filename",
                            "progress_thumbnail")
                           )
                
        # Just for you, Daniel.
        try:
            if os.getlogin() == "daniels":
                self.window.set_title("Respecognise")
        except Exception:
            pass
        
        self.model = gtk.ListStore (gobject.TYPE_STRING, # COL_FILENAME
                                    gtk.gdk.Pixbuf, # COL_IMAGE
                                    gtk.gdk.Pixbuf, # COL_PREVIEW
                                    gtk.gdk.Pixbuf,  #COL_THUMBNAIL
                                    gobject.TYPE_STRING, # COL_TITLE
                                    gobject.TYPE_STRING, # COL_DESCRIPTION
                                    gobject.TYPE_STRING) # COL_TAGS
        self.current_it = None

        # last opened folder
        self.last_folder = None

        self.change_signals = []
        self.change_signals.append((self.title_entry, self.title_entry.connect('changed', self.on_field_changed, COL_TITLE)))
        self.change_signals.append((self.desc_entry, self.desc_entry.connect('changed', self.on_field_changed, COL_DESCRIPTION)))
        self.change_signals.append((self.tags_entry, self.tags_entry.connect('changed', self.on_field_changed, COL_TAGS)))
        self.thumbnail_image.connect('size-allocate', self.update_thumbnail)
        self.old_thumb_allocation = None

        self.iconview.set_model (self.model)
        self.iconview.set_text_column (COL_TITLE)
        self.iconview.set_pixbuf_column (COL_THUMBNAIL)
    
        self.iconview.drag_dest_set (gtk.DEST_DEFAULT_ALL, (), gtk.gdk.ACTION_COPY)
        targets = ()
        targets = gtk.target_list_add_image_targets(targets, DRAG_IMAGE, False)
        targets = gtk.target_list_add_uri_targets(targets, DRAG_URI)
        self.iconview.drag_dest_set_target_list(targets)

        # The upload progress dialog
        self.uploading = False
        self.progress_dialog.set_transient_for(self.window)
        # Disable the Upload menu until the user has authenticated
        self.upload_menu.set_sensitive(False)
        
        # Connect to flickr, go go go
        self.token = self.flickr.authenticate_1().addCallback(self.auth_open_url)
    
    def on_message(self, app, command, command_data, startup_id, screen, workspace):
        """Callback from UniqueApp, when a message arrives."""
        if command == gtkunique.OPEN:
            self.add_image_filename(command_data)
            return gtkunique.RESPONSE_OK
        else:
            return gtkunique.RESPONSE_ABORT

    def auth_open_url(self, state):
        """Callback from midway through Flickr authentication.  At this point we
        either have cached tokens so can carry on, or need to open a web browser
        to authenticate the user."""
        if state is None:
            self.connected(True)
        else:
            dialog = AuthenticationDialog(self.window, state['url'])
            if dialog.run() == gtk.RESPONSE_ACCEPT:
                self.flickr.authenticate_2(state).addCallback(self.connected)
            dialog.destroy()
    
    def connected(self, connected):
        """Callback when the Flickr authentication completes."""
        if connected:
            self.upload_menu.set_sensitive(True)
            self.flickr.people_getUploadStatus().addCallback(self.got_quota)

    def got_quota(self, rsp):
        """Callback for the getUploadStatus call, which updates the remaining
        quota in the status bar."""
        bandwidth = rsp.find("user/bandwidth").get("remainingbytes")
        context = self.statusbar.get_context_id("quota")
        self.statusbar.pop(context)
        self.statusbar.push(context, _("You have %s remaining this month") %
                            greek(int(bandwidth)))

    def on_field_changed(self, entry, column):
        """Callback when the entry fields are changed."""
        items = self.iconview.get_selected_items()
        for path in items:
            it = self.model.get_iter(path)
            self.model.set_value (it, column, entry.get_text())
    
    def on_add_photos_activate(self, menuitem):
        """Callback from the File->Add Photos menu item."""
        dialog = gtk.FileChooserDialog(title=_("Add Photos"), parent=self.window,
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=(gtk.STOCK_CANCEL,
                                                gtk.RESPONSE_CANCEL,
                                                gtk.STOCK_OPEN,
                                                gtk.RESPONSE_OK))
        dialog.set_select_multiple(True)
        if self.last_folder:
            dialog.set_current_folder(self.last_folder)

        # Add filters for all reasonable image types
        filters = gtk.FileFilter()
        filters.set_name(_("Images"))
        filters.add_mime_type("image/png")
        filters.add_mime_type("image/jpeg")
        filters.add_mime_type("image/gif")
        dialog.add_filter(filters)
        filters = gtk.FileFilter()
        filters.set_name(_("All Files"))
        filters.add_pattern("*")
        dialog.add_filter(filters)

        # Add a preview widget
        preview = gtk.Image()
        dialog.set_preview_widget(preview)
        def update_preview_cb(file_chooser, preview):
            filename = file_chooser.get_preview_filename()
            try:
                pixbuf = gtk.gdk.pixbuf_new_from_file_at_size(filename, 128, 128)
                preview.set_from_pixbuf(pixbuf)
                have_preview = True
            except:
                have_preview = False
            file_chooser.set_preview_widget_active(have_preview)
        dialog.connect("update-preview", update_preview_cb, preview)
        
        if dialog.run() == gtk.RESPONSE_OK:
            dialog.hide()
            for f in dialog.get_filenames():
                self.add_image_filename(f)
            
            self.last_folder = dialog.get_current_folder()

        dialog.destroy()
            
    def on_quit_activate(self, widget, *args):
        """Callback from File->Quit."""
        if self.uploading:
            dialog = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, parent=self.window)
            dialog.add_buttons(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                               gtk.STOCK_QUIT, gtk.RESPONSE_OK)
            dialog.set_markup(_('<b>Currently Uploading</b>'))
            dialog.format_secondary_text(_('Photos are still being uploaded. '
                                         'Are you sure you want to quit?'))
            response = dialog.run()
            dialog.destroy()
            if response == gtk.RESPONSE_CANCEL:
                return True
        
        import twisted.internet.reactor
        twisted.internet.reactor.stop()
    
    def on_delete_activate(self, menuitem):
        """Callback from Edit->Delete."""
        selection = self.iconview.get_selected_items()
        for path in selection:
            self.model.remove(self.model.get_iter(path))
    
    def on_select_all_activate(self, menuitem):
        """Callback from Edit->Select All."""
        self.iconview.select_all()

    def on_deselect_all_activate(self, menuitem):
        """Callback from Edit->Deselect All."""
        self.iconview.unselect_all()

    def on_invert_selection_activate(self, menuitem):
        """Callback from Edit->Invert Selection."""
        selected = self.iconview.get_selected_items()
        def inverter(model, path, iter, selected):
            if path in selected:
                self.iconview.unselect_path(path)
            else:
                self.iconview.select_path(path)
        self.model.foreach(inverter, selected)

    def on_upload_activate(self, menuitem):
        """Callback from File->Upload."""
        if self.uploading:
            print "Upload should be disabled, currently uploading"
            return
        
        it = self.model.get_iter_first()
        if it is None:
            print "Upload should be disabled, no photos"
            return

        menuitem.set_sensitive(False)
        self.uploading = True
        self.iconview.set_sensitive(False)
        self.progress_dialog.show()

        self.upload_count = self.model.iter_n_children (None)
        self.upload_index = 0
        self.upload()
        
    def on_about_activate(self, menuitem):
        """Callback from Help->About."""
        dialog = AboutDialog(self.window)
        dialog.run()
        dialog.destroy()

    def update_thumbnail(self, widget, allocation = None):
        """Update the preview, as the selected image was changed."""
        if self.current_it:
            if not allocation:
                allocation = widget.get_allocation()
                force = True
            else:
                force = False

            # hrngh.  seemingly a size-allocate call (with identical params,
            # mind) gets called every time we call set_from_pixbuf.  even if
            # we connect it to the window.  so very braindead.
            if not force and self.old_thumb_allocation and \
               self.old_thumb_allocation.width == allocation.width and \
               self.old_thumb_allocation.height == allocation.height:
                return;

            self.old_thumb_allocation = allocation

            (image, simage, filename) = self.model.get(self.current_it,
                                                       COL_IMAGE,
                                                       COL_PREVIEW,
                                                       COL_FILENAME)

            tw = allocation.width
            th = allocation.height
            # Clamp the size to 512
            if tw > 512: tw = 512
            if th > 512: th = 512
            (tw, th) = self.get_thumb_size(simage.get_width(),
                                           simage.get_height(),
                                           tw, th)

            thumb = simage.scale_simple(tw, th, gtk.gdk.INTERP_BILINEAR)
            widget.set_from_pixbuf(thumb)

    def on_selection_changed(self, iconview):
        """Callback when the selection was changed, to update the entries and
        preview."""
        [obj.handler_block(i) for obj,i in self.change_signals]
        
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
            (title, desc, tags) = self.model.get(self.current_it,
                                                 COL_TITLE,
                                                 COL_DESCRIPTION,
                                                 COL_TAGS)

            enable_field(self.title_entry, title)
            enable_field(self.desc_entry, desc)
            enable_field(self.tags_entry, tags)

            self.update_thumbnail(self.thumbnail_image)
        else:
            self.current_it = None
            disable_field(self.title_entry)
            disable_field(self.desc_entry)
            disable_field(self.tags_entry)

            self.thumbnail_image.set_from_pixbuf(None)

        [obj.handler_unblock(i) for obj,i in self.change_signals]

    @staticmethod
    def get_thumb_size(srcw, srch, dstw, dsth):
        """Scale scrw x srch to an dimensions with the same ratio that fits as
        closely as possible to dstw x dsth."""
        ratio = srcw/float(srch)
        if srcw > srch:
            return (dstw, int(dstw/ratio))
        else:
            return (int(dsth*ratio), dsth)

    def add_image_filename(self, filename):
        """Add a file to the image list.  Called by the File->Add Photo and drag
        and drop callbacks."""
        # TODO: MIME type check

        # TODO: we open the file three times now, which is madness, especially
        # if gnome-vfs is used to read remote files.  Need to find/write EXIF
        # and IPTC parsers that are incremental.
        
        # On a file that doesn't contain EXIF, like a PNG, this just returns an
        # empty set.
        exif = EXIF.process_file(open(filename, 'rb'))
        iptc = IPTC.getiptc(open(filename, 'rb'))
        
        # First we load the image scaled to 512x512 for the preview.
        preview = gtk.gdk.pixbuf_new_from_file_at_size(filename, 512, 512)

        # Rotate the preview if required.  We don't need to manipulate the
        # original data as Flickr will do that for us.
        rotation = exif.get("Image Orientation", None)
        if rotation:
            rotation = rotation.values[0]
            if rotation == ROTATED_180:
                preview = preview.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
            elif rotation == ROTATED_90_CW:
                preview = preview.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
            elif rotation == ROTATED_90_CCW:
                preview = preview.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
        
        # Now scale the preview to a thumbnail
        sizes = self.get_thumb_size(preview.get_width(), preview.get_height(), 64, 64)
        thumb = preview.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)

        # Slurp data from the EXIF and IPTC tags
        title_tags = (
            (iptc, "Caption"),
            )
        desc_tags = (
            (exif, "Image ImageDescription"),
            (exif, "UserComment"),
            )
        tag_tags = (
            (iptc, "Keywords"),
            )
        def slurp(tags, default=""):
            for (data, tag) in tags:
                if data.has_key(tag):
                    return data[tag]
            return default
        
        title = slurp(title_tags, os.path.splitext(os.path.basename(filename))[0])
        desc = slurp(desc_tags)
        tags = slurp(tag_tags)
        
        self.model.set(self.model.append(),
                       COL_FILENAME, filename,
                       COL_IMAGE, None,
                       COL_PREVIEW, preview,
                       COL_THUMBNAIL, thumb,
                       COL_TITLE, title,
                       COL_DESCRIPTION, desc,
                       COL_TAGS, tags)
    
    def on_drag_data_received(self, widget, context, x, y, selection, targetType, timestamp):
        """Drag and drop callback when data is received."""
        if targetType == DRAG_IMAGE:
            pixbuf = selection.get_pixbuf()

            # TODO: don't scale up if the image is smaller than 512/512
            
            # Scale the pixbuf to a preview
            sizes = self.get_thumb_size (pixbuf.get_width(), pixbuf.get_height(), 512, 512)
            preview = pixbuf.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)
            # Now scale to a thumbnail
            sizes = self.get_thumb_size (pixbuf.get_width(), pixbuf.get_height(), 64, 64)
            thumb = pixbuf.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)
            
            self.model.set(self.model.append(),
                           COL_IMAGE, pixbuf,
                           COL_FILENAME, None,
                           COL_PREVIEW, preview,
                           COL_THUMBNAIL, thumb,
                           COL_TITLE, "",
                           COL_DESCRIPTION, "",
                           COL_TAGS, "")
        
        elif targetType == DRAG_URI:
            for uri in selection.get_uris():
                # TODO: use gnome-vfs to handle remote files
                filename = urlparse(uri)[2]
                if os.path.isfile(filename):
                    self.add_image_filename(filename)
                elif os.path.isdir(filename):
                    for root, dirs, files in os.walk(filename):
                        for f in files:
                            # TODO: handle symlinks to directories as they are
                            # in files
                            self.add_image_filename (os.path.join(root, f))
                else:
                    print "Unhandled file %s" % filename
                    
        else:
            print "Unhandled target type %d" % targetType
        
        context.finish(True, True, timestamp)

    def update_progress(self, title, filename, thumb):
        """Update the progress bar whilst uploading."""
        label = '<b>%s</b>\n<i>%s</i>' % (title, basename(filename))
        self.progress_filename.set_label(label)

        try:
            self.progress_thumbnail.set_from_pixbuf(thumb)
            self.progress_thumbnail.show()
        except:
            self.progress_thumbnail.set_from_pixbuf(None)
            self.progress_thumbnail.hide()

        self.progressbar.set_fraction(float(self.upload_index) / float(self.upload_count))
        progress_label = _('Uploading %d of %d') % (self.upload_index+1, self.upload_count)
        self.progressbar.set_text(progress_label)

    def upload(self, response=None):
        """Upload worker function, called by the File->Upload callback.  As this
        calls itself in the deferred callback, it takes a response argument."""
        if self.upload_index >= self.upload_count:
            self.upload_menu.set_sensitive(True)
            self.uploading = False
            self.progress_dialog.hide()
            self.model.clear()
            self.iconview.set_sensitive(True)
            self.flickr.people_getUploadStatus().addCallback(self.got_quota)
            return

        it = self.model.get_iter_from_string(str(self.upload_index))
        (filename, thumb, pixbuf, title, desc, tags) = self.model.get(it,
                                                                      COL_FILENAME,
                                                                      COL_THUMBNAIL,
                                                                      COL_IMAGE,
                                                                      COL_TITLE,
                                                                      COL_DESCRIPTION,
                                                                      COL_TAGS)
        self.update_progress(filename, title, thumb)
        self.upload_index += 1

        if filename:
            self.flickr.upload(filename=filename,
                               title=title, desc=desc,
                               tags=tags).addCallback(self.upload)
        elif pixbuf:
            # This isn't very nice, but might be the best way
            data = []
            pixbuf.save_to_callback(lambda d: data.append(d), "png", {})
            self.flickr.upload(imageData=''.join(data),
                                title=title, desc=desc,
                                tags=tags).addCallback(self.upload)
        else:
            print "No filename or pixbuf stored"

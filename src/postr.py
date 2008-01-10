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

import logging, os, urllib
from urlparse import urlparse
from os.path import basename

import pygtk; pygtk.require ("2.0")
import gobject, gtk, gtk.glade, gconf

from AboutDialog import AboutDialog
from AuthenticationDialog import AuthenticationDialog
from ProgressDialog import ProgressDialog
from ErrorDialog import ErrorDialog
import ImageStore, ImageList, StatusBar, PrivacyCombo, SafetyCombo

from flickrest import Flickr
from twisted.web.client import getPage
import EXIF
from iptcinfo import IPTCInfo
from util import *


try:
    from gtkunique import UniqueApp
except ImportError:
    from DummyUnique import UniqueApp

#logging.basicConfig(level=logging.DEBUG)

# Exif information about image orientation
(ROTATED_0,
 ROTATED_180,
 ROTATED_90_CW,
 ROTATED_90_CCW
 ) = (1, 3, 6, 8)


class Postr (UniqueApp):
    def __init__(self):
        UniqueApp.__init__(self, 'com.burtonini.Postr')
        try:
            self.connect("message", self.on_message)
        except AttributeError:
            pass

        self.is_connected = False
        
        self.flickr = Flickr(api_key="c53cebd15ed936073134cec858036f1d",
                             secret="7db1b8ef68979779",
                             perms="write")

        gtk.window_set_default_icon_name("postr")
        gtk.glade.set_custom_handler(self.get_custom_handler)
        glade = gtk.glade.XML(os.path.join (os.path.dirname(__file__), "postr.glade"))
        glade.signal_autoconnect(self)

        get_glade_widgets (glade, self,
                           ("window",
                            "upload_menu",
                            "upload_button",
                            "statusbar",
                            "thumbnail_image",
                            "title_entry",
                            "desc_view",
                            "tags_entry",
                            "set_combo",
                            "privacy_combo",
                            "safety_combo",
                            "visible_check",
                            "thumbview")
                           )
        align_labels(glade, ("title_label", "desc_label", "tags_label", "set_label", "privacy_label", "safety_label"))
        
        # Just for you, Daniel.
        try:
            if os.getlogin() == "daniels":
                self.window.set_title("Respecognise")
        except Exception:
            pass
        
        self.model = ImageStore.ImageStore ()
        self.model.connect("row-inserted", self.on_model_changed)
        self.model.connect("row-deleted", self.on_model_changed)
        
        self.thumbview.set_model(self.model)
        self.thumbview.connect("drag_data_received", self.on_drag_data_received)

        selection = self.thumbview.get_selection()
        selection.connect("changed", self.on_selection_changed)

        self.current_it = None
        self.last_folder = None
        self.upload_quota = None

        self.thumbnail_image.clear()
        self.thumbnail_image.set_size_request(1, 1)
        
        self.change_signals = []
        self.change_signals.append((self.title_entry, self.title_entry.connect('changed', self.on_field_changed, ImageStore.COL_TITLE)))
        self.change_signals.append((self.desc_view.get_buffer(), self.desc_view.get_buffer().connect('changed', self.on_field_changed, ImageStore.COL_DESCRIPTION)))
        self.change_signals.append((self.tags_entry, self.tags_entry.connect('changed', self.on_field_changed, ImageStore.COL_TAGS)))
        self.change_signals.append((self.visible_check, self.visible_check.connect('toggled', self.on_field_changed, ImageStore.COL_VISIBLE)))
        
        self.thumbnail_image.connect('size-allocate', self.update_thumbnail)
        self.old_thumb_allocation = None

        # The set selector combo
        self.sets = gtk.ListStore (gobject.TYPE_STRING, # ID
                                   gobject.TYPE_STRING, # Name
                                   gtk.gdk.Pixbuf) # Thumbnail
        self.sets.set (self.sets.append(), 0, None, 1, "None")
        self.set_combo.set_model (self.sets)
        self.set_combo.set_active (-1)
        
        renderer = gtk.CellRendererPixbuf()
        self.set_combo.pack_start (renderer, expand=False)
        self.set_combo.set_attributes(renderer, pixbuf=2)
        renderer = gtk.CellRendererText()
        self.set_combo.pack_start (renderer, expand=False)
        self.set_combo.set_attributes(renderer, text=1)
        
        # The upload progress dialog
        self.uploading = False
        self.current_upload_it = None
        self.cancel_upload = False
        def cancel():
            self.cancel_upload = True
        self.progress_dialog = ProgressDialog(cancel)
        self.progress_dialog.set_transient_for(self.window)
        # Disable the Upload menu until the user has authenticated
        self.update_upload()

        # Update the proxy configuration
        client = gconf.client_get_default()
        client.add_dir("/system/http_proxy", gconf.CLIENT_PRELOAD_RECURSIVE)
        client.notify_add("/system/http_proxy", self.proxy_changed)
        self.proxy_changed(client, 0, None, None)
        
        # Connect to flickr, go go go
        self.flickr.authenticate_1().addCallbacks(self.auth_open_url, self.twisted_error)
    
    def twisted_error(self, failure):
        self.update_upload()
        
        dialog = ErrorDialog(self.window)
        dialog.set_from_failure(failure)
        dialog.show_all()

    def proxy_changed(self, client, cnxn_id, entry, something):
        if client.get_bool("/system/http_proxy/use_http_proxy"):
            host = client.get_string("/system/http_proxy/host")
            port = client.get_int("/system/http_proxy/port")
            if host is None or host == "" or port == 0:
                self.flickr.set_proxy(None)
                return
            
            if client.get_bool("/system/http_proxy/use_authentication"):
                user = client.get_string("/system/http_proxy/authentication_user")
                password = client.get_string("/system/http_proxy/authentication_password")
                if user and user != "":
                    url = "http://%s:%s@%s:%d" % (user, password, host, port)
                else:
                    url = "http://%s:%d" % (host, port)
            else:
                url = "http://%s:%d" % (host, port)

            self.flickr.set_proxy(url)
        else:
            self.flickr.set_proxy(None)
    
    def get_custom_handler(self, glade, function_name, widget_name, str1, str2, int1, int2):
        """libglade callback to create custom widgets."""
        try:
            handler = getattr(self, function_name)
            return handler(str1, str2, int1, int2)
        except:
            widget = eval(function_name)
            widget.show()
            return widget
    
    def image_list_new (self, *args):
        """Custom widget creation function to make the image list."""
        view = ImageList.ImageList ()
        view.show()
        return view

    def status_bar_new (self, *args):
        bar = StatusBar.StatusBar(self.flickr)
        bar.show()
        return bar
    
    def on_message(self, app, command, command_data, startup_id, screen, workspace):
        """Callback from UniqueApp, when a message arrives."""
        if command == gtkunique.OPEN:
            self.add_image_filename(command_data)
            return gtkunique.RESPONSE_OK
        else:
            return gtkunique.RESPONSE_ABORT

    def on_model_changed(self, *args):
        # We don't care about the arguments, because we just want to know when
        # the model was changed, not what was changed.
        self.update_upload()
    
    def auth_open_url(self, state):
        """Callback from midway through Flickr authentication.  At this point we
        either have cached tokens so can carry on, or need to open a web browser
        to authenticate the user."""
        if state is None:
            self.connected(True)
        else:
            dialog = AuthenticationDialog(self.window, state['url'])
            if dialog.run() == gtk.RESPONSE_ACCEPT:
                self.flickr.authenticate_2(state).addCallbacks(self.connected, self.twisted_error)
            dialog.destroy()
    
    def connected(self, connected):
        """Callback when the Flickr authentication completes."""
        self.is_connected = connected
        if connected:
            self.update_upload()
            self.statusbar.update_quota()
            self.flickr.photosets_getList().addCallbacks(self.got_photosets, self.twisted_error)

    def update_upload(self):
        connected = self.is_connected and self.model.iter_n_children(None) > 0
        self.upload_menu.set_sensitive(connected)
        self.upload_button.set_sensitive(connected)

    def update_statusbar(self):
        """Recalculate how much is to be uploaded, and update the status bar."""
        size = 0
        for row in self.model:
            size += row[ImageStore.COL_SIZE]
        self.statusbar.set_upload(size)
    
    def got_set_thumb(self, page, it):
        loader = gtk.gdk.PixbufLoader()
        loader.set_size (32, 32)
        loader.write(page)
        loader.close()
        self.sets.set (it, 2, loader.get_pixbuf())
    
    def got_photosets(self, rsp):
        """Callback for the photosets.getList call"""
        for photoset in rsp.findall("photosets/photoset"):
            it = self.sets.append()
            self.sets.set (it,
                           0, photoset.get("id"),
                           1, photoset.find("title").text)

            url = "http://static.flickr.com/%s/%s_%s%s.jpg" % (photoset.get("server"), photoset.get("primary"), photoset.get("secret"), "_s")
            getPage (url).addCallback (self.got_set_thumb, it).addErrback(self.twisted_error)
    
    def on_field_changed(self, widget, column):
        """Callback when the entry fields are changed."""
        if isinstance(widget, gtk.Entry) or isinstance(widget, gtk.TextBuffer):
            value = widget.get_property("text")
        elif isinstance(widget, gtk.ToggleButton):
            value = widget.get_active()
        else:
            raise "Unhandled widget type %s" % widget
        
        selection = self.thumbview.get_selection()
        (model, items) = selection.get_selected_rows()
        for path in items:
            it = self.model.get_iter(path)
            self.model.set_value (it, column, value)

    def on_set_combo_changed(self, combo):
        """Callback when the set combo is changed."""
        set_it = self.set_combo.get_active_iter()
        selection = self.thumbview.get_selection()
        (model, items) = selection.get_selected_rows()
        for path in items:
            it = self.model.get_iter(path)
            self.model.set_value (it, ImageStore.COL_SET, set_it)
    
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
        filters.add_mime_type("image/*")
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
            self.last_folder = dialog.get_current_folder()
            for f in dialog.get_filenames():
                self.add_image_filename(f)
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
    
    def on_remove_activate(self, menuitem):
        """Callback from File->Remove."""
        selection = self.thumbview.get_selection()
        (model, items) = selection.get_selected_rows()
        
        # Remove the items
        for path in items:
            self.model.remove(self.model.get_iter(path))

        # Select a new row
        try:
            self.thumbview.set_cursor(self.model[items[0]].path)
        except IndexError:
            # TODO: It appears that the ability to simply do
            # gtk_tree_path_previous() is missing in PyGTK.
            path = list(items[-1])
            if path[0]:
                path[0] -= 1
                self.thumbview.set_cursor(self.model[tuple(path)].path)
        
        self.update_statusbar()
        
    def on_select_all_activate(self, menuitem):
        """Callback from Edit->Select All."""
        selection = self.thumbview.get_selection()
        selection.select_all()

    def on_deselect_all_activate(self, menuitem):
        """Callback from Edit->Deselect All."""
        selection = self.thumbview.get_selection()
        selection.unselect_all()

    def on_invert_selection_activate(self, menuitem):
        """Callback from Edit->Invert Selection."""
        selection = self.thumbview.get_selection()
        selected = selection.get_selected_rows()[1]
        for row in self.model:
            if row.path in selected:
                selection.unselect_iter(row.iter)
            else:
                selection.select_iter(row.iter)

    def on_upload_activate(self, menuitem):
        """Callback from File->Upload."""
        if self.uploading:
            print "Upload should be disabled, currently uploading"
            return
        
        it = self.model.get_iter_first()
        if it is None:
            print "Upload should be disabled, no photos"
            return

        self.upload_menu.set_sensitive(False)
        self.upload_button.set_sensitive(False)
        self.uploading = True
        self.thumbview.set_sensitive(False)
        self.progress_dialog.show()

        self.upload_count = self.model.iter_n_children (None)
        self.upload_index = 0
        self.upload()
        
    def on_about_activate(self, menuitem):
        """Callback from Help->About."""
        dialog = AboutDialog()
        dialog.set_transient_for(self.window)
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

            (simage,) = self.model.get(self.current_it, ImageStore.COL_PREVIEW)
            
            tw = allocation.width
            th = allocation.height
            # Clamp the size to 512
            if tw > 512: tw = 512
            if th > 512: th = 512
            (tw, th) = get_thumb_size(simage.get_width(),
                                           simage.get_height(),
                                           tw, th)

            thumb = simage.scale_simple(tw, th, gtk.gdk.INTERP_BILINEAR)
            widget.set_from_pixbuf(thumb)

    def on_selection_changed(self, selection):
        """Callback when the selection was changed, to update the entries and
        preview."""
        [obj.handler_block(i) for obj,i in self.change_signals]
        
        def enable_field(field, value):
            field.set_sensitive(True)
            if isinstance(field, gtk.Entry):
                field.set_text(value)
            elif isinstance(field, gtk.TextView):
                field.get_buffer().set_text (value)
            elif isinstance(field, gtk.ToggleButton):
                field.set_active(value)
            else:
                raise "Unhandled widget type %s" % field
        def disable_field(field):
            field.set_sensitive(False)
            if isinstance(field, gtk.Entry):
                field.set_text("")
            elif isinstance(field, gtk.TextView):
                field.get_buffer().set_text ("")
            elif isinstance(field, gtk.ToggleButton):
                field.set_active(True)
            else:
                raise "Unhandled widget type %s" % field

        (model, items) = selection.get_selected_rows()
        
        if items:
            # TODO: do something clever with multiple selections
            self.current_it = self.model.get_iter(items[0])
            (title, desc, tags, set_it, visible) = self.model.get(self.current_it,
                                                                  ImageStore.COL_TITLE,
                                                                  ImageStore.COL_DESCRIPTION,
                                                                  ImageStore.COL_TAGS,
                                                                  ImageStore.COL_SET,
                                                                  ImageStore.COL_VISIBLE)

            enable_field(self.title_entry, title)
            enable_field(self.desc_view, desc)
            enable_field(self.tags_entry, tags)
            enable_field(self.visible_check, visible)
            self.set_combo.set_sensitive(True)
            if (set_it):
                self.set_combo.set_active_iter(set_it)
            else:
                self.set_combo.set_active(0)
            self.update_thumbnail(self.thumbnail_image)
        else:
            self.current_it = None
            disable_field(self.title_entry)
            disable_field(self.desc_view)
            disable_field(self.tags_entry)
            self.set_combo.set_sensitive(False)
            self.set_combo.set_active(-1)
            disable_field(self.visible_check)

            self.thumbnail_image.set_from_pixbuf(None)

        [obj.handler_unblock(i) for obj,i in self.change_signals]

    def add_image_filename(self, filename):
        """Add a file to the image list.  Called by the File->Add Photo and drag
        and drop callbacks."""
        # TODO: MIME type check

        # Check the file size
        filesize = os.path.getsize(filename)
        if filesize > 10 * 1024 * 1024:
            d = ErrorDialog(self.window)
            d.set_from_string("Image %s is too large, images must be no larger than 10MB in size." % filename)
            d.show_all()
            return
        
        # TODO: we open the file three times now, which is madness, especially
        # if gnome-vfs is used to read remote files.  Need to find/write EXIF
        # and IPTC parsers that are incremental.
        
        # First we load the image scaled to 512x512 for the preview.
        try:
            preview = gtk.gdk.pixbuf_new_from_file_at_size(filename, 512, 512)
        except Exception, e:
            d = ErrorDialog(self.window)
            d.set_from_exception(e)
            d.show_all()
            return
        
        # On a file that doesn't contain EXIF, like a PNG, this just returns an
        # empty set.
        try:
            exif = EXIF.process_file(open(filename, 'rb'))
        except:
            exif = {}
        try:
            iptc = IPTCInfo(open(filename, 'rb')).data
        except:
            iptc = {}
        
        # Rotate the preview if required.  We don't need to manipulate the
        # original data as Flickr will do that for us.
        if "Image Orientation" in exif:
            rotation = exif["Image Orientation"].values[0]
            if rotation == ROTATED_180:
                preview = preview.rotate_simple(gtk.gdk.PIXBUF_ROTATE_UPSIDEDOWN)
            elif rotation == ROTATED_90_CW:
                preview = preview.rotate_simple(gtk.gdk.PIXBUF_ROTATE_CLOCKWISE)
            elif rotation == ROTATED_90_CCW:
                preview = preview.rotate_simple(gtk.gdk.PIXBUF_ROTATE_COUNTERCLOCKWISE)
        
        # Now scale the preview to a thumbnail
        sizes = get_thumb_size(preview.get_width(), preview.get_height(), 64, 64)
        thumb = preview.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)

        # Slurp data from the EXIF and IPTC tags
        title_tags = (
            (iptc, "headline"),
            )
        desc_tags = (
            (exif, "Image ImageDescription"),
            (exif, "UserComment"),
            (iptc, "caption/abstract"),
            )
        tag_tags = (
            (iptc, "keywords"),
            )
        def slurp(tags, default=""):
            for (data, tag) in tags:
                if data.has_key(tag):
                    value = data[tag]
                    if isinstance (value, list):
                        return ' '.join(map (lambda s: '"' + s + '"', value))
                    elif not isinstance (value, str):
                        value = str(value)
                    if value:
                        return value
            return default
        
        title = slurp(title_tags, os.path.splitext(os.path.basename(filename))[0])
        desc = slurp(desc_tags)
        tags = slurp(tag_tags)
        
        self.model.set(self.model.append(),
                       ImageStore.COL_FILENAME, filename,
                       ImageStore.COL_SIZE, filesize,
                       ImageStore.COL_IMAGE, None,
                       ImageStore.COL_PREVIEW, preview,
                       ImageStore.COL_THUMBNAIL, thumb,
                       ImageStore.COL_TITLE, title,
                       ImageStore.COL_DESCRIPTION, desc,
                       ImageStore.COL_TAGS, tags,
                       ImageStore.COL_VISIBLE, True)

        self.update_statusbar()
        self.update_upload()
    
    def on_drag_data_received(self, widget, context, x, y, selection, targetType, timestamp):
        """Drag and drop callback when data is received."""
        if targetType == ImageList.DRAG_IMAGE:
            pixbuf = selection.get_pixbuf()

            # TODO: don't scale up if the image is smaller than 512/512
            
            # Scale the pixbuf to a preview
            sizes = get_thumb_size (pixbuf.get_width(), pixbuf.get_height(), 512, 512)
            preview = pixbuf.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)
            # Now scale to a thumbnail
            sizes = get_thumb_size (pixbuf.get_width(), pixbuf.get_height(), 64, 64)
            thumb = pixbuf.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)

            # TODO: This is wrong, and should generate a PNG here and use the
            # size of the PNG
            size = pixbuf.get_width() * pixbuf.get_height() * pixbuf.get_n_channels()
            
            self.model.set(self.model.append(),
                           ImageStore.COL_IMAGE, pixbuf,
                           ImageStore.COL_SIZE, size,
                           ImageStore.COL_FILENAME, None,
                           ImageStore.COL_PREVIEW, preview,
                           ImageStore.COL_THUMBNAIL, thumb,
                           ImageStore.COL_TITLE, "",
                           ImageStore.COL_DESCRIPTION, "",
                           ImageStore.COL_TAGS, "",
                           ImageStore.COL_VISIBLE, True)

        
        elif targetType == ImageList.DRAG_URI:
            for uri in selection.get_uris():
                # TODO: use gnome-vfs to handle remote files
                filename = urllib.unquote(urlparse(uri)[2])
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

        self.update_statusbar()
        context.finish(True, True, timestamp)

    def update_progress(self, title, filename, thumb):
        """Update the progress bar whilst uploading."""
        label = '<b>%s</b>\n<i>%s</i>' % (title, basename(filename))
        self.progress_dialog.label.set_label(label)

        try:
            self.progress_dialog.thumbnail.set_from_pixbuf(thumb)
            self.progress_dialog.thumbnail.show()
        except:
            self.progress_dialog.thumbnail.set_from_pixbuf(None)
            self.progress_dialog.thumbnail.hide()

        self.progress_dialog.progress.set_fraction(float(self.upload_index) / float(self.upload_count))

        # Use named args for i18n
        data = {
            "index": self.upload_index+1,
            "count": self.upload_count
            }
        progress_label = _('Uploading %(index)d of %(count)d') % data
        self.progress_dialog.label.set_text(progress_label)

        self.window.set_title(_('Flickr Uploader (%(index)d/%(count)d)') % data)

    def add_to_set(self, rsp, set):
        """Callback from the upload method to add the picture to a set."""
        self.flickr.photosets_addPhoto(photoset_id=set,
                                       photo_id=rsp.find("photoid").text)
        return rsp

    def upload_done(self):
        self.cancel_upload = False
        self.window.set_title(_("Flickr Uploader"))
        self.upload_menu.set_sensitive(True)
        self.upload_button.set_sensitive(True)
        self.uploading = False
        self.progress_dialog.hide()
        self.thumbview.set_sensitive(True)
        self.statusbar.update_quota()

    def upload_error(self, failure):
        self.twisted_error(failure)
        self.upload_done()
        
    def upload(self, response=None):
        """Upload worker function, called by the File->Upload callback.  As this
        calls itself in the deferred callback, it takes a response argument."""

        # Remove the uploaded image from the store
        if self.current_upload_it:
            self.model.remove(self.current_upload_it)
            self.current_upload_it = None
        
        it = self.model.get_iter_first()
        if self.cancel_upload or it is None:
            self.upload_done()
            return

        (filename, thumb, pixbuf, title, desc, tags, set_it, visible) = self.model.get(it,
                                                                                       ImageStore.COL_FILENAME,
                                                                                       ImageStore.COL_THUMBNAIL,
                                                                                       ImageStore.COL_IMAGE,
                                                                                       ImageStore.COL_TITLE,
                                                                                       ImageStore.COL_DESCRIPTION,
                                                                                       ImageStore.COL_TAGS,
                                                                                       ImageStore.COL_SET,
                                                                                       ImageStore.COL_VISIBLE)
        # Lookup the set ID from the iterator
        if set_it:
            (set_id,) = self.sets.get (set_it, 0)
        else:
            set_id = 0
        
        self.update_progress(filename, title, thumb)
        self.upload_index += 1
        self.current_upload_it = it
        
        if filename:
            d = self.flickr.upload(filename=filename,
                               title=title, desc=desc,
                               tags=tags, search_hidden=not visible)
            if set_id:
                d.addCallback(self.add_to_set, set_id)
            d.addCallbacks(self.upload, self.upload_error)
        elif pixbuf:
            # This isn't very nice, but might be the best way
            data = []
            pixbuf.save_to_callback(lambda d: data.append(d), "png", {})
            d = self.flickr.upload(imageData=''.join(data),
                                title=title, desc=desc,
                                tags=tags, search_hidden=not visible)
            if set_id:
                d.addCallback(self.add_to_set, set_id)
            d.addCallbacks(self.upload, self.upload_error)
        else:
            print "No filename or pixbuf stored"

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

import os, urllib
from urlparse import urlparse
from os.path import basename

import pygtk; pygtk.require ("2.0")
import gobject, gtk, gtk.glade, gconf, gio
import gnome.ui

from AboutDialog import AboutDialog
from AuthenticationDialog import AuthenticationDialog
from ProgressDialog import ProgressDialog
from ErrorDialog import ErrorDialog
import ImageStore, ImageList, StatusBar, PrivacyCombo, SafetyCombo, GroupSelector, ContentTypeCombo
from proxyclient import EXTRA_STEP_SET_ID, EXTRA_STEP_GROUPS, EXTRA_STEP_LICENSE, EXTRA_STEP_NEW_SET, UploadProgressTracker

from flickrest import Flickr
import EXIF
from iptcinfo import IPTCInfo
from util import *
from datetime import datetime
import shelve

try:
    import PyUnique
    from PyUnique import UniqueApp
except ImportError:
    from DummyUnique import UniqueApp

# Exif information about image orientation
(ROTATED_0,
 ROTATED_180,
 ROTATED_90_CW,
 ROTATED_90_CCW
 ) = (1, 3, 6, 8)

_FILE_ATTRIBUTES = ",".join([gio.FILE_ATTRIBUTE_STANDARD_TYPE,
                             gio.FILE_ATTRIBUTE_STANDARD_NAME,
                             gio.FILE_ATTRIBUTE_STANDARD_SIZE,
                             gio.FILE_ATTRIBUTE_STANDARD_DISPLAY_NAME])

class Postr(UniqueApp):
    def __init__(self):
        UniqueApp.__init__(self, 'com.burtonini.Postr')
        try:
            self.connect("message-received", self.on_message_pyunique)
        except AttributeError:
            pass

        self.is_connected = False
        
        self.flickr = Flickr(api_key="c437f34483b22367cff3ed8a2103b626",
                             secret="73231c8a993b4c62",
                             perms="write")

        self.logo_icon_size = gtk.icon_size_register("logo", 128, 128)
        
        gtk.window_set_default_icon_name("postr")
        gtk.glade.set_custom_handler(self.get_custom_handler)
        glade = gtk.glade.XML(os.path.join(os.path.dirname(__file__), "postr.glade"))
        glade.signal_autoconnect(self)

        get_glade_widgets(glade, self,
                           ("window",
                            "upload_menu",
                            "upload_button",
                            "remove_menu",
                            "remove_button",
                            "save_session_menu",
                            "avatar_image",
                            "statusbar",
                            "thumbnail_image",
                            "info_table",
                            "title_entry",
                            "desc_view",
                            "tags_entry",
                            "set_combo",
                            "rename_button",
                            "group_selector",
                            "privacy_combo",
                            "safety_combo",
                            "visible_check",
                            "content_type_combo",
                            "license_combo",
                            "thumbview")
                           )
        align_labels(glade, ("title_label", "desc_label",
                             "tags_label", "set_label",
                             "privacy_label", "safety_label"))
        
        # Just for you, Daniel.
        try:
            if os.getlogin() == "daniels":
                self.window.set_title("Respecognise")
        except Exception:
            pass
        
        self.model = ImageStore.ImageStore()
        self.model.connect("row-inserted", self.on_model_changed)
        self.model.connect("row-deleted", self.on_model_changed)
        
        self.thumbview.set_model(self.model)

        self.set_combo.connect("changed", self.on_set_combo_changed)
        
        selection = self.thumbview.get_selection()
        selection.connect("changed", self.on_selection_changed)

        self.drag_signals = []
        self.drag_signals.append((self.thumbview, self.thumbview.connect(
                            "drag_data_received", self.on_drag_data_received)))

        self.thumbview.connect("row-activated",
                               self.on_row_activated,
                               self.title_entry)

        self.drop_disabled = False
        self.drag_started = False

        self.thumbview.connect("button_press_event",
                                self.on_button_press_cb)
        self.thumbview.connect("button_release_event",
                                self.on_button_release_cb)
        self.thumbview.connect("drag_begin", self.drag_begin_cb)
        self.thumbview.connect("drag_end", self.drag_end_cb)

        # TODO: remove this
        self.current_it = None
        self.last_folder = None
        self.upload_quota = None

        self.thumbnail_image.clear()
        self.thumbnail_image.set_size_request(128, 128)
        
        self.change_signals = [] # List of (widget, signal ID) tuples
        self.change_signals.append((self.title_entry, self.title_entry.connect('changed', self.on_field_changed, ImageStore.COL_TITLE)))
        self.change_signals.append((self.desc_view.get_buffer(), self.desc_view.get_buffer().connect('changed', self.on_field_changed, ImageStore.COL_DESCRIPTION)))
        self.change_signals.append((self.tags_entry, self.tags_entry.connect('changed', self.on_field_changed, ImageStore.COL_TAGS)))
        self.change_signals.append((self.group_selector, self.group_selector.connect('changed', self.on_field_changed, ImageStore.COL_GROUPS)))
        self.change_signals.append((self.privacy_combo, self.privacy_combo.connect('changed', self.on_field_changed, ImageStore.COL_PRIVACY)))
        self.change_signals.append((self.safety_combo, self.safety_combo.connect('changed', self.on_field_changed, ImageStore.COL_SAFETY)))
        self.change_signals.append((self.visible_check, self.visible_check.connect('toggled', self.on_field_changed, ImageStore.COL_VISIBLE)))
        self.change_signals.append((self.content_type_combo, self.content_type_combo.connect('changed', self.on_field_changed, ImageStore.COL_CONTENT_TYPE)))
        self.change_signals.append((self.license_combo, self.license_combo.connect('changed', self.on_field_changed, ImageStore.COL_LICENSE)))
        
        self.thumbnail_image.connect('size-allocate', self.update_thumbnail)
        self.old_thumb_allocation = None

        self.on_selection_changed(selection)
        
        # The upload progress dialog
        self.uploading = False
        self.current_upload_it = None
        self.cancel_upload = False
        def cancel():
            self.cancel_upload = True
        self.progress_dialog = ProgressDialog(cancel)
        self.progress_dialog.set_transient_for(self.window)
        self.upload_progress_tracker = UploadProgressTracker(self.progress_dialog.image_progress)
        self.avatar_image.clear()
        # Disable the Upload menu until the user has authenticated
        self.update_upload()

        # We don't have any photos yet, disable remove buttons
        self.update_remove()

        # Update the proxy configuration
        client = gconf.client_get_default()
        client.add_dir("/system/http_proxy", gconf.CLIENT_PRELOAD_RECURSIVE)
        client.notify_add("/system/http_proxy", self.proxy_changed)
        self.proxy_changed(client, 0, None, None)
        
        # Connect to flickr, go go go
        self.flickr.authenticate_1().addCallbacks(self.auth_open_url, self.twisted_error)

    def open_uri(self, uri):
        return self.send_message(self.commands['OPEN'], uri)

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
        handler = getattr(self, function_name, None)
        if handler:
            return handler(str1, str2, int1, int2)
        else:
            widget = eval(function_name)
            widget.show()
            return widget

    def group_selector_new(self, *args):
        w = GroupSelector.GroupSelector(self.flickr)
        w.show()
        return w

    def set_combo_new(self, *args):
        import SetCombo
        w = SetCombo.SetCombo(self.flickr)
        w.show()
        return w

    def license_combo_new(self, *args):
        import LicenseCombo
        w = LicenseCombo.LicenseCombo(self.flickr)
        w.show()
        return w
    
    def image_list_new(self, *args):
        """Custom widget creation function to make the image list."""
        view = ImageList.ImageList()
        view.show()
        return view

    def status_bar_new(self, *args):
        bar = StatusBar.StatusBar(self.flickr)
        bar.show()
        return bar
    def tag_entry_new(self, *args):
        import TagsEntry
        entry = TagsEntry.TagsEntry(self.flickr)
        return entry

    def on_message_pyunique(self, instance, command, data):
        """ PyUnique callback for receiving a message """
        if command == self.commands['OPEN']:
            self.add_image_filename(data)
            self.window.present()
            return PyUnique.RESPONSE_OK
        else:
            return PyUnique.RESPONSE_INVALID

    def on_model_changed(self, *args):
        # We don't care about the arguments, because we just want to know when
        # the model was changed, not what was changed.
        self.update_upload()
        self.update_remove()
    
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
            self.group_selector.update()
            self.set_combo.update()
            self.license_combo.update()
            self.update_avatar()
            self.update_tag_list()

    def on_statusbar_box_expose(self, widget, event):
        """
        Expose callback for the event box containing the status bar, to paint it
        in a different colour.
        """
        widget.window.draw_rectangle(widget.style.dark_gc[gtk.STATE_NORMAL], True, *event.area)
        
    def update_upload(self):
        connected = self.is_connected and self.model.iter_n_children(None) > 0
        self.upload_menu.set_sensitive(connected)
        self.upload_button.set_sensitive(connected)

    def update_remove(self):
        have_photos = self.model.iter_n_children(None) > 0
        self.remove_menu.set_sensitive(have_photos)
        self.remove_button.set_sensitive(have_photos)
        self.save_session_menu.set_sensitive(have_photos)

    def update_statusbar(self):
        """Recalculate how much is to be uploaded, and update the status bar."""
        size = 0
        for row in self.model:
            size += row[ImageStore.COL_SIZE]
        self.statusbar.set_upload(size)
    
    def update_avatar(self):
        """
        Update the avatar displayed at the top of the window.  Called when
        authentication is completed.
        """
        def getinfo_cb(rsp):
            p = rsp.find("person")
            data = {
                "nsid": self.flickr.get_nsid(),
                "iconfarm": p.get("iconfarm"),
                "iconserver": p.get("iconserver")
            }
            def get_buddyicon_cb(icon):
                self.avatar_image.set_from_pixbuf(icon)
            get_buddyicon(self.flickr, data).addCallbacks(get_buddyicon_cb, self.twisted_error)
        # Need to call people.getInfo to get the iconserver/iconfarm
#TX
#        self.flickr.people_findById(user_id=self.flickr.get_nsid()).addCallbacks(getinfo_cb, self.twisted_error)
    
    def on_field_changed(self, widget, column):
        """Callback when the entry fields are changed."""
        if isinstance(widget, gtk.Entry) or isinstance(widget, gtk.TextBuffer):
            value = widget.get_property("text")
        elif isinstance(widget, gtk.ToggleButton):
            value = widget.get_active()
        elif isinstance(widget, gtk.ComboBox):
            value = widget.get_active_iter()
        elif isinstance(widget, GroupSelector.GroupSelector):
            value = widget.get_selected_groups()
        else:
            raise "Unhandled widget type %s" % widget
        selection = self.thumbview.get_selection()
        (model, items) = selection.get_selected_rows()
        self._set_value_in_model(column, value, items)

    def _set_value_in_model(self, column, value, rows):
        for path in rows:
            it = self.model.get_iter(path)
            self.model.set_value(it, column, value)

    # TODO: remove this and use the field-changed logic
    def on_set_combo_changed(self, combo):
        """Callback when the set combo is changed."""
        set_it = self.set_combo.get_active_iter()

        (id, ) = self.set_combo.get_id_for_iter(set_it) if set_it else (None, )
        self._update_rename_button(id)

        selection = self.thumbview.get_selection()
        (model, items) = selection.get_selected_rows()
        for path in items:
            it = self.model.get_iter(path)
            self.model.set_value(it, ImageStore.COL_SET, set_it)

    def _update_rename_button(self, id):
        if id == '-1':
            self.info_table.child_set(self.set_combo,
                                      "right-attach",
                                      2)
            self.rename_button.set_sensitive(True)
        else:
            self.info_table.child_set(self.set_combo,
                                      "right-attach",
                                      3)
            self.rename_button.set_sensitive(False)

    def on_rename_activate(self, button):
        self.set_combo.name_new_photoset()

    def on_add_photos_activate(self, widget):
        """Callback from the File->Add Photos menu item or Add button."""
        dialog = gtk.FileChooserDialog(title=_("Add Photos"), parent=self.window,
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=(gtk.STOCK_CANCEL,
                                                gtk.RESPONSE_CANCEL,
                                                gtk.STOCK_OPEN,
                                                gtk.RESPONSE_OK))
        dialog.set_select_multiple(True)
        if self.last_folder:
            dialog.set_current_folder_uri(self.last_folder)

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

        def get_thumbnail(uri):
            # Given a uri, return a Pixbuf with the thumbnail or
            # None in case is not possible to get it or
            # generate it.

            gfile = gio.File(uri)
            ginfo = gfile.query_info('time::modified,standard::content-type')
            mtime = ginfo.get_modification_time()
            mime = ginfo.get_content_type()

            factory = gnome.ui.ThumbnailFactory(gnome.ui.THUMBNAIL_SIZE_NORMAL)
            thumb_path = factory.lookup(uri, int(mtime))

            if thumb_path:
                return gtk.gdk.pixbuf_new_from_file(thumb_path)

            # There is no thumbmail, we will try to generate one
            # or return None if not possible
            if factory.can_thumbnail(uri, mime, int(mtime)):
                thumbnail = factory.generate_thumbnail(uri, mime)
                if thumbnail is not None:
                    factory.save_thumbnail(thumbnail, uri, int(mtime))
                return thumbnail
            else:
                return None

        def update_preview_cb(file_chooser, preview):
            filename = file_chooser.get_preview_filename()
            uri = file_chooser.get_preview_uri()

            if uri:
                thumbnail = get_thumbnail(uri)

            if uri and thumbnail:
                preview.set_from_pixbuf(thumbnail)
                have_preview = True
            else:
                have_preview = False

            file_chooser.set_preview_widget_active(have_preview)

        dialog.connect("update-preview", update_preview_cb, preview)
        
        if dialog.run() == gtk.RESPONSE_OK:
            dialog.hide()
            self.last_folder = dialog.get_current_folder_uri()
            for uri in dialog.get_uris():
                self.add_image_uri(uri)
        dialog.destroy()
            
    def on_quit_activate(self, widget, *args):
        """Callback from File->Quit."""
        if self.uploading:
            dialog = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, parent=self.window)
            dialog.add_buttons(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                               gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT,
                               gtk.STOCK_QUIT, gtk.RESPONSE_OK)
            dialog.set_markup(_('<b>Currently Uploading</b>'))
            dialog.format_secondary_text(_('Photos are still being uploaded. '
                                           'Are you sure you want to quit? '
                                           'You can also save your pending upload set for later.'))
            dialog.set_default_response(gtk.RESPONSE_OK)
            response = dialog.run()
            dialog.destroy()
            if response == gtk.RESPONSE_CANCEL:
                return True
            elif response == gtk.RESPONSE_ACCEPT:
                self.save_upload_set()
        elif self.is_connected and self.model.iter_n_children(None) > 0 and self.model.dirty():
            dialog = gtk.MessageDialog(type=gtk.MESSAGE_WARNING, parent=self.window)
            dialog.add_buttons(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                               gtk.STOCK_SAVE, gtk.RESPONSE_ACCEPT,
                               gtk.STOCK_QUIT, gtk.RESPONSE_OK)
            dialog.set_markup(_('<b>Photos to be uploaded</b>'))
            dialog.format_secondary_text(_('There are photos pending to '
                                           'be uploaded. '
                                           'Are you sure you want to quit? '
                                           'You can also save your pending upload set for later.'))
            dialog.set_default_response(gtk.RESPONSE_OK)
            response = dialog.run()
            dialog.destroy()
            if response == gtk.RESPONSE_CANCEL:
                return True
            elif response == gtk.RESPONSE_ACCEPT:
                self.save_upload_set()

        import twisted.internet.reactor
        twisted.internet.reactor.stop()

    def on_save_session_activate(self, widget):
        """Callback from File->Save session."""
        self.save_upload_set()

    def on_load_session_activate(self, widget):
        self.load_upload_set()

    def on_remove_activate(self, widget):
        """Callback from File->Remove or Remove button."""
        
        def get_selected_iter(model, path, iter, selectList):
            selectIter = model.get_iter(path)
            selectList.append(selectIter)

        select_list = []

        selection = self.thumbview.get_selection()
        selection.selected_foreach(get_selected_iter, select_list)
        model = self.thumbview.get_model()

        next_select_iter = model.iter_next(select_list[-1])

        # actual removal of rows
        for iter in select_list:
            model.remove(iter)

        self.update_statusbar()

        if next_select_iter:
            self.thumbview.set_cursor(model.get_path(next_select_iter))
        elif len(model) > 0:
            self.thumbview.set_cursor(model[-1].path)


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

    def on_switch_activate(self, menuitem):
        """Callback from File->Switch User."""
        self.flickr.clear_cached()
        self.flickr.authenticate_1().addCallbacks(self.auth_open_url, self.twisted_error)
    
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
        self.remove_menu.set_sensitive(False)
        self.remove_button.set_sensitive(False)
        self.rename_button.set_sensitive(False)
        self.uploading = True
        self.thumbview.set_sensitive(False)
        self.progress_dialog.show()

        self.upload_count = self.model.iter_n_children(None)
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
                field.get_buffer().set_text(value)
            elif isinstance(field, gtk.ToggleButton):
                field.set_active(value)
            elif isinstance(field, gtk.ComboBox):
                if value:
                    field.set_active_iter(value)
                else:
                    # This means the default value is always the first
                    field.set_active(0)
            elif isinstance(field, GroupSelector.GroupSelector):
                field.set_selected_groups(value)
            else:
                raise "Unhandled widget type %s" % field
        def disable_field(field):
            field.set_sensitive(False)
            if isinstance(field, gtk.Entry):
                field.set_text("")
            elif isinstance(field, gtk.TextView):
                field.get_buffer().set_text("")
            elif isinstance(field, gtk.ToggleButton):
                field.set_active(True)
            elif isinstance(field, gtk.ComboBox):
                field.set_active(-1)
            elif isinstance(field, GroupSelector.GroupSelector):
                field.set_selected_groups(())
            else:
                raise "Unhandled widget type %s" % field

        (model, items) = selection.get_selected_rows()

        if items:
            # TODO: do something clever with multiple selections
            self.current_it = self.model.get_iter(items[0])
            (title, desc, tags, set_it, groups,
             privacy_it, safety_it, visible,
             content_type_it, license_it) = self.model.get(self.current_it,
                           ImageStore.COL_TITLE,
                           ImageStore.COL_DESCRIPTION,
                           ImageStore.COL_TAGS,
                           ImageStore.COL_SET,
                           ImageStore.COL_GROUPS,
                           ImageStore.COL_PRIVACY,
                           ImageStore.COL_SAFETY,
                           ImageStore.COL_VISIBLE,
                           ImageStore.COL_CONTENT_TYPE,
                           ImageStore.COL_LICENSE)

            enable_field(self.title_entry, title)
            enable_field(self.desc_view, desc)
            enable_field(self.tags_entry, tags)
            enable_field(self.set_combo, set_it)
            enable_field(self.group_selector, groups)
            enable_field(self.privacy_combo, privacy_it)
            enable_field(self.safety_combo, safety_it)
            enable_field(self.visible_check, visible)
            enable_field(self.content_type_combo, content_type_it)
            enable_field(self.license_combo, license_it)

            self.update_thumbnail(self.thumbnail_image)
        else:
            self.current_it = None
            disable_field(self.title_entry)
            disable_field(self.desc_view)
            disable_field(self.tags_entry)
            disable_field(self.set_combo)
            disable_field(self.group_selector)
            disable_field(self.privacy_combo)
            disable_field(self.safety_combo)
            disable_field(self.visible_check)
            disable_field(self.content_type_combo)
            disable_field(self.license_combo)

            self.thumbnail_image.set_from_icon_name("postr", self.logo_icon_size)
        [obj.handler_unblock(i) for obj,i in self.change_signals]

    def add_image_dir_file(self, gfile):
        children = gfile.enumerate_children(_FILE_ATTRIBUTES, flags=gio.FILE_QUERY_INFO_NONE)
        child_info = children.next_file()
        while child_info:
            file_type = child_info.get_file_type()
            if file_type == gio.FILE_TYPE_REGULAR:
                self.add_image_fileinfo(gfile, child_info)
            elif file_type == gio.FILE_TYPE_DIRECTORY:
                dirname = os.path.join(gfile.get_uri(), child_info.get_name())
                self.add_image_dir_file(gio.File(dirname))
            else:
                print "Unhandled file %s" % gfile.get_uri()
            child_info = children.next_file()
        children.close()

    def add_image_uri(self, uri):
        """Add a file to the image list.  Called by the File->Add Photo and drag
        and drop callbacks."""
        return self.add_image_filename(uri)

    def add_image_filename(self, filename):
        gfile = gio.File(filename)
        fileinfo = gfile.query_info(_FILE_ATTRIBUTES, flags=gio.FILE_QUERY_INFO_NONE)
        self.add_image_file(gfile, fileinfo)

    def add_image_fileinfo(self, parent, fileinfo):
        filename = os.path.join(parent.get_uri(), fileinfo.get_name())
        gfile = gio.File(filename)
        self.add_image_file(gfile, fileinfo)

    def _on_preview_size_prepared(self, loader, width, height):
        """Appropriately scale the image preview to fit inside 512x512"""
        if width > height:
            new_width = 512
            new_height = 512 * height / width
        else:
            new_width = 512 * width / height
            new_height = 512
        loader.set_size(new_width, new_height)

    def add_image_file(self, gfile, fileinfo):
        filesize = fileinfo.get_size()
        if filesize > self.statusbar.maxfile * 1024 * 1024:
            d = ErrorDialog(self.window)
            d.set_from_string(_("Image %s is too large, images must be no larger than %dMB in size.") % (gfile.get_path(), self.statusbar.maxfile))
            d.show_all()
            return
        
        # TODO: we open the file three times now, which is madness, especially
        # if gnome-vfs is used to read remote files.  Need to find/write EXIF
        # and IPTC parsers that are incremental.

        # only opening the file_stream
        file_stream = gfile.read()

        # First we load the image scaled to 512x512 for the preview.
        try:
            if gfile.is_native():
                preview = gtk.gdk.pixbuf_new_from_file_at_size(gfile.get_path(), 512, 512)
            else:
                loader = gtk.gdk.PixbufLoader()
                loader.connect("size-prepared", self._on_preview_size_prepared)
                loader.write(file_stream.read())
                loader.close()
                preview = loader.get_pixbuf()
        except Exception, e:
            d = ErrorDialog(self.window)
            d.set_from_exception(e)
            d.show_all()
            return
        
        # type 1 is beginning of file
        if not file_stream.can_seek() or not file_stream.seek(0, type=1):
            file_stream = gfile.read()

        # On a file that doesn't contain EXIF, like a PNG, this just returns an
        # empty set.
        try:
            exif = EXIF.process_file(file_stream)
        except:
            exif = {}

        # type 1 is beginning of file
        if not file_stream.can_seek() or not file_stream.seek(0, type=1):
            file_stream = gfile.read()

        try:
            iptc = IPTCInfo(file_stream).data
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
                    if isinstance(value, list):
                        return ' '.join(map(lambda s: '"' + s + '"', value))
                    elif not isinstance(value, str):
                        value = str(value)
                    if value:
                        return value
            return default
        
        title = slurp(title_tags, os.path.splitext(fileinfo.get_display_name())[0])
        desc = slurp(desc_tags)
        tags = slurp(tag_tags)
        
        self.model.set(self.model.append(),
                       ImageStore.COL_URI, gfile.get_uri(),
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
            sizes = get_thumb_size(pixbuf.get_width(), pixbuf.get_height(), 512, 512)
            preview = pixbuf.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)
            # Now scale to a thumbnail
            sizes = get_thumb_size(pixbuf.get_width(), pixbuf.get_height(), 64, 64)
            thumb = pixbuf.scale_simple(sizes[0], sizes[1], gtk.gdk.INTERP_BILINEAR)

            # TODO: This is wrong, and should generate a PNG here and use the
            # size of the PNG
            size = pixbuf.get_width() * pixbuf.get_height() * pixbuf.get_n_channels()
            
            self.model.set(self.model.append(),
                           ImageStore.COL_IMAGE, pixbuf,
                           ImageStore.COL_SIZE, size,
                           ImageStore.COL_URI, None,
                           ImageStore.COL_PREVIEW, preview,
                           ImageStore.COL_THUMBNAIL, thumb,
                           ImageStore.COL_TITLE, "",
                           ImageStore.COL_DESCRIPTION, "",
                           ImageStore.COL_TAGS, "",
                           ImageStore.COL_VISIBLE, True)

        
        elif targetType == ImageList.DRAG_URI:
            for uri in selection.get_uris():
                gfile = gio.File(uri)
                fileinfo = gfile.query_info(_FILE_ATTRIBUTES)
                file_type = fileinfo.get_file_type()
                if file_type == gio.FILE_TYPE_REGULAR:
                    self.add_image_file(gfile, fileinfo)
                elif file_type == gio.FILE_TYPE_DIRECTORY:
                    self.add_image_dir_file(gfile)
                else:
                    print "Unhandled file %s" % gfile.get_uri()
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
        photo_id=rsp.find("photoid").text
        self.flickr.albums_addPhoto(photo_id=photo_id, photoset_id=set).addErrback(self.twisted_error)
        self.upload_progress_tracker.complete_extra_step(EXTRA_STEP_SET_ID)
        return rsp

    def add_to_groups(self, rsp, groups):
        """Callback from the upload method to add the picture to a groups."""
        photo_id=rsp.find("photoid").text
        for group in groups:
            def error(failure):
                # Code 6 means "moderated", which isn't an error
                if failure.value.code != 6:
                    self.twisted_error(failure)
            self.flickr.groups_pools_add(photo_id=photo_id, group_id=group).addErrback(error)
        self.upload_progress_tracker.complete_extra_step(EXTRA_STEP_GROUPS)
        return rsp

    def set_license(self, rsp, license):
        """Callback from the upload method to set license for the picture."""
        photo_id=rsp.find("photoid").text
        self.flickr.photos_licenses_setLicense(photo_id=photo_id,
                                               license_id=license).addErrback(self.twisted_error)
        self.upload_progress_tracker.complete_extra_step(EXTRA_STEP_LICENSE)
        return rsp

    def upload_done(self):
        self.cancel_upload = False
        self.window.set_title(_("Flickr Uploader"))
        self.upload_menu.set_sensitive(True)
        self.upload_button.set_sensitive(True)
        self.update_remove()
        self.uploading = False
        self.progress_dialog.hide()
        self.thumbview.set_sensitive(True)
        self.update_statusbar()
        self.statusbar.update_quota()
        self.current_upload_it = None

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

        (uri, thumb, pixbuf, title, desc,
         tags, set_it, groups, privacy_it, safety_it,
         visible, content_type_it, license_it) = self.model.get(it,
                       ImageStore.COL_URI,
                       ImageStore.COL_THUMBNAIL,
                       ImageStore.COL_IMAGE,
                       ImageStore.COL_TITLE,
                       ImageStore.COL_DESCRIPTION,
                       ImageStore.COL_TAGS,
                       ImageStore.COL_SET,
                       ImageStore.COL_GROUPS,
                       ImageStore.COL_PRIVACY,
                       ImageStore.COL_SAFETY,
                       ImageStore.COL_VISIBLE,
                       ImageStore.COL_CONTENT_TYPE,
                       ImageStore.COL_LICENSE)
        # Lookup the set ID from the iterator
        if set_it:
            (set_id,) = self.set_combo.get_id_for_iter(set_it)
            if set_id == '-1':
                new_photoset_name = self.set_combo.new_photoset_name
                set_id = 0
            else:
                new_photoset_name = None
        else:
            set_id = 0
            new_photoset_name = None

        if privacy_it:
            (is_public, is_family, is_friend) = self.privacy_combo.get_acls_for_iter(privacy_it)
        else:
            is_public = is_family = is_friend = None

        if safety_it:
            safety = self.safety_combo.get_safety_for_iter(safety_it)
        else:
            safety = None

        if content_type_it:
            content_type = self.content_type_combo.get_content_type_for_iter(content_type_it)
        else:
            content_type = None

        if license_it:
            license = self.license_combo.get_license_for_iter(license_it)
        else:
            license = None

        self.update_progress(uri, title, thumb)
        self.upload_index += 1
        self.current_upload_it = it

        if uri:
            d = self.flickr.upload(uri=uri,
                                   title=title, desc=desc,
                                   tags=tags, search_hidden=not visible, safety=safety,
                                   is_public=is_public, is_family=is_family, is_friend=is_friend,
                                   content_type=content_type, progress_tracker=self.upload_progress_tracker)
        elif pixbuf:
            # This isn't very nice, but might be the best way
            data = []
            pixbuf.save_to_callback(lambda d: data.append(d), "png", {})
            d = self.flickr.upload(imageData=''.join(data),
                                   title=title, desc=desc, tags=tags,
                                   search_hidden=not visible, safety=safety,
                                   is_public=is_public, is_family=is_family, is_friend=is_friend,
                                   content_type=content_type, progress_tracker=self.upload_progress_tracker)
        else:
            print "No filename or pixbuf stored"

        if set_id:
            d.addCallback(self.add_to_set, set_id)
        else:
            self.upload_progress_tracker.complete_extra_step(EXTRA_STEP_SET_ID)
        if groups:
            d.addCallback(self.add_to_groups, groups)
        else:
            self.upload_progress_tracker.complete_extra_step(EXTRA_STEP_GROUPS)
        if license is not None: # 0 is a valid license.
            d.addCallback(self.set_license, license)
        else:
            self.upload_progress_tracker.complete_extra_step(EXTRA_STEP_LICENSE)
        # creating a new photoset has implications on subsequent uploads,
        # so this has to finish before starting the next upload
        if new_photoset_name:
            d.addCallback(self.create_photoset_then_continue, new_photoset_name)
        else:
            d.addCallbacks(self.upload, self.upload_error)
            self.upload_progress_tracker.complete_extra_step(EXTRA_STEP_NEW_SET)

    def create_photoset_then_continue(self, rsp, photoset_name):
        photo_id=rsp.find("photoid").text
        create_photoset = self.flickr.albums_create(primary_photo_id=photo_id, title=photoset_name)
        create_photoset.addCallback(self._process_photoset_creation, photoset_name)
        create_photoset.addErrback(self.upload_error)
        return rsp

    def _process_photoset_creation(self, create_rsp, photoset_name):
        photoset = create_rsp.find("photoset")
        id = photoset.get("id")
        self.set_combo.set_recently_created_photoset(photoset_name, id)
        self.upload(create_rsp)
        return create_rsp

    def on_row_activated(self, treeview, iter, path, entry):
        """This callback is used to focus the entry title after
            one row is activated."""
        entry.grab_focus()

    def drag_begin_cb(self, thumbview, context, data=None):
        self.drag_started = True

    def drag_end_cb(self, thumbview, context, data=None):
        self.drop_disabled = False
        self.drag_started = False
        self.thumbview.set_reorderable(False)

        self.thumbview.enable_targets()
        [obj.handler_unblock(i) for obj,i in self.drag_signals]

    def on_button_press_cb(self, thumbview, event, data=None):
        if self.drop_disabled:
            return
        self.thumbview.unable_targets()

        self.drop_disabled = True
        [obj.handler_block(i) for obj,i in self.drag_signals]
        thumbview.set_reorderable(True)
        return

    def on_button_release_cb(self, thumbview, event, data=None):

        if self.drop_disabled and (not self.drag_started):
            self.drop_disabled = False
            thumbview.set_reorderable(False)
            self.thumbview.enable_targets()
            [obj.handler_unblock(i) for obj,i in self.drag_signals]
        return False


    def save_upload_set(self):
        dialog = gtk.FileChooserDialog(title=None,
                                       action=gtk.FILE_CHOOSER_ACTION_SAVE,
                                       buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                                gtk.STOCK_SAVE, gtk.RESPONSE_OK))

        dialog.set_default_response(gtk.RESPONSE_OK)

        default_filename = datetime.strftime(datetime.today(), "upload_saved_on_%m-%d-%y.postr")
        dialog.set_current_name(default_filename)

        dialog.set_do_overwrite_confirmation(True)

        filter = gtk.FileFilter()
        filter.set_name("postr upload sets")
        filter.add_pattern("*.postr")
        dialog.add_filter(filter)

        filter = gtk.FileFilter()
        filter.set_name("All Files")
        filter.add_pattern("*")
        dialog.add_filter(filter)

        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filename()
            dest = shelve.open(filename, 'n')

            if self.is_connected:
                dest["nsid"] = self.flickr.get_nsid()
                username = self.flickr.get_username()
                if username:
                    dest["username"] = username

            if self.set_combo.new_photoset_name:
                dest["new_photoset_name"] = self.set_combo.new_photoset_name

            iter = self.model.get_iter_root()
            while iter:
                path = self.model.get_string_from_iter(iter)
                dest[path] = self._marshal_row(path, iter)
                iter = self.model.iter_next(iter)

            dest.close()
            self.model.markClean()

        dialog.destroy()

    def _marshal_row(self, path, iter):
        (uri,
         title,
         desc,
         tags,
         set_it,
         groups,
         privacy_it,
         safety_it,
         visible) = self.model.get(iter,
                                   ImageStore.COL_URI,
                                   ImageStore.COL_TITLE,
                                   ImageStore.COL_DESCRIPTION,
                                   ImageStore.COL_TAGS,
                                   ImageStore.COL_SET,
                                   ImageStore.COL_GROUPS,
                                   ImageStore.COL_PRIVACY,
                                   ImageStore.COL_SAFETY,
                                   ImageStore.COL_VISIBLE)

        if set_it:
            # Can't use path, because next time we connect, the
            # combo order/contents might be different.
            (set_id,) = self.set_combo.get_id_for_iter(set_it)
        else:
            set_id = 0

        if privacy_it:
            privacy_path = self.privacy_combo.model.get_path(privacy_it)
        else:
            privacy_path = None

        if safety_it:
            safety_path = self.safety_combo.model.get_path(safety_it)
        else:
            safety_path = None

        args = ( path,
                 uri,
                 title,
                 desc,
                 tags,
                 set_id,
                 groups,
                 privacy_path,
                 safety_path,
                 visible )
        return args

    def load_upload_set(self):
        dialog = gtk.FileChooserDialog(title=None,
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                                                gtk.STOCK_OPEN, gtk.RESPONSE_OK))

        dialog.set_default_response(gtk.RESPONSE_OK)

        filter = gtk.FileFilter()
        filter.set_name("postr upload sets")
        filter.add_pattern("*.postr")
        dialog.add_filter(filter)

        filter = gtk.FileFilter()
        filter.set_name("All Files")
        filter.add_pattern("*")
        dialog.add_filter(filter)

        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filename()
            source = shelve.open(filename, 'r')
            if source:
                should_ignore_albums = False
                if self.is_connected:
                    if source.has_key("nsid"):
                        nsid = source["nsid"]
                        username = source.get("username")

                        if self.flickr.get_nsid() != nsid:
                            markup_args = (self.flickr.get_username(), username) if self.flickr.get_username() and username else (self.flickr.get_nsid(), nsid)
                            markup_pattern = _("You are logged in as %s but loading\nan upload set for %s")
                            confirm_dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO)
                            confirm_dialog.set_default_response(gtk.RESPONSE_YES)
                            confirm_dialog.set_markup(markup_pattern % markup_args)
                            confirm_dialog.format_secondary_text(_("Do you want to continue "
                                                                   "with the load?  You will "
                                                                   "not import photoset information."))
                            response = confirm_dialog.run()
                            if response == gtk.RESPONSE_NO:
                                dialog.destroy()
                                return
                            else:
                                should_ignore_albums = True
                            confirm_dialog.destroy()
                else:
                    if source.has_key("nsid"):
                        source_user = source.get("username", source["nsid"])
                        markup_pattern = _("You are not logged in but loading\nan upload set for %s")
                        confirm_dialog = gtk.MessageDialog(buttons=gtk.BUTTONS_YES_NO)
                        confirm_dialog.set_default_response(gtk.RESPONSE_YES)
                        confirm_dialog.set_markup(markup_pattern % source_user)
                        confirm_dialog.format_secondary_text(_("Do you want to continue "
                                                               "with the load?  You will "
                                                               "not import photoset information."))
                        response = confirm_dialog.run()
                        if response == gtk.RESPONSE_NO:
                            dialog.destroy()
                            return
                        else:
                            should_ignore_albums = True
                        confirm_dialog.destroy()

                if source.has_key("new_photoset_name"):
                    self.set_combo.update_new_photoset(source["new_photoset_name"])

                # the model's dirty state should not be changed
                # when loading an upload set.
                model_was_dirty = self.model.dirty()

                index_offset = self.model.iter_n_children(None)
                index = 0
                while source.has_key(str(index)):
                    row = source[str(index)]
                    self._unmarshal_and_import_row(index + index_offset,
                                                   row,
                                                   should_ignore_albums)
                    index += 1
                source.close()

                # obviously a load will make the model dirty, but that
                # information is already saved, so ensure that the model
                # is only dirty after a load if it was dirty before
                if not model_was_dirty:
                    self.model.markClean()

        dialog.destroy()

    def _unmarshal_and_import_row(self, index, row, should_ignore_albums):
        (path, uri, title, desc, tags, set_id, groups, privacy_path, safety_path, visible) = row

        self.add_image_uri(uri)
        self._set_value_in_model(ImageStore.COL_TITLE, title, [index])
        self._set_value_in_model(ImageStore.COL_DESCRIPTION, desc, [index])
        self._set_value_in_model(ImageStore.COL_TAGS, tags, [index])

        if not should_ignore_albums and set_id:
            set_iter = self.set_combo.get_iter_for_set(set_id)
            if set_iter:
                self._set_value_in_model(ImageStore.COL_SET, set_iter, [index])

        self._set_value_in_model(ImageStore.COL_GROUPS, groups, [index])

        if privacy_path:
            privacy_iter = self.privacy_combo.model.get_iter(privacy_path)
            self._set_value_in_model(ImageStore.COL_PRIVACY, privacy_iter, [index])

        if safety_path:
            safety_iter = self.safety_combo.model.get_iter(safety_path)
            self._set_value_in_model(ImageStore.COL_SAFETY, safety_iter, [index])
        self._set_value_in_model(ImageStore.COL_VISIBLE, visible, [index])

    def update_tag_list(self):
        self.tags_entry.update()


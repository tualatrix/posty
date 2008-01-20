import gobject, gtk, pango
from ErrorDialog import ErrorDialog
import util

class GroupSelector(gtk.TreeView):
    def __init__(self, flickr):
        self.flickr = flickr
        self.model = gtk.ListStore(gobject.TYPE_STRING, gtk.gdk.Pixbuf)
        gtk.TreeView.__init__(self, self.model)
        self.set_headers_visible(False)
        
        column = gtk.TreeViewColumn('')
        self.append_column(column)
        
        renderer =  gtk.CellRendererToggle()
        column.pack_start(renderer, False)
        #column.add_attribute(renderer, "text", 0)
        
        renderer =  gtk.CellRendererPixbuf()
        column.pack_start(renderer, False)
        column.add_attribute(renderer, "pixbuf", 1)
        
        renderer =  gtk.CellRendererText()
        column.pack_start(renderer, True)
        column.add_attribute(renderer, "text", 0)

    def update(self):
        self.flickr.groups_pools_getGroups().addCallbacks(self.got_groups, self.twisted_error)
    
    def got_groups(self, rsp):
        from elementtree.ElementTree import dump
        for group in rsp.findall("groups/group"):
            it = self.model.append()
            self.model.set (it, 0, group.get("name"))
            def got_thumb(thumb, it):
                self.model.set (it, 1, thumb)
            util.get_buddyicon(self.flickr, group).addCallback(got_thumb, it)
        
    def twisted_error(self, failure):
        dialog = ErrorDialog(self.window)
        dialog.set_from_failure(failure)
        dialog.show_all()

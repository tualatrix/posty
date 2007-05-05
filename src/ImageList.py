import gtk
import pango 

import ImageStore

# Constants for the drag handling
(DRAG_URI,
 DRAG_IMAGE) = range (0, 2)

class ImageList(gtk.TreeView):
    def __init__(self):
        gtk.TreeView.__init__(self)

        column = gtk.TreeViewColumn('Preview', 
                                     gtk.CellRendererPixbuf(),
                                    pixbuf=ImageStore.COL_THUMBNAIL)

        self.append_column(column)

        renderer =  gtk.CellRendererText()
        renderer.set_property('ellipsize', pango.ELLIPSIZE_END) 

        column = gtk.TreeViewColumn('Info', 
                                    renderer,
                                    markup=ImageStore.COL_INFO)
 
        self.append_column(column)

        self.set_headers_visible(False)
        self.set_enable_search(False)

        selection = self.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)

        # Setup the drag and drop
        self.drag_dest_set (gtk.DEST_DEFAULT_ALL, (), gtk.gdk.ACTION_COPY)
        targets = ()
        targets = gtk.target_list_add_image_targets (targets, DRAG_IMAGE, False)
        targets = gtk.target_list_add_uri_targets (targets, DRAG_URI)
        self.drag_dest_set_target_list (targets)

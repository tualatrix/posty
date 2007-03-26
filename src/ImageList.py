import gtk

import ImageStore

# Constants for the drag handling
(DRAG_URI,
 DRAG_IMAGE) = range (0, 2)

class ImageList(gtk.IconView):
    def __init__(self, model=None):
        gtk.IconView.__init__(self, model)
        
        self.set_selection_mode (gtk.SELECTION_MULTIPLE)
        self.set_text_column (ImageStore.COL_TITLE)
        self.set_pixbuf_column (ImageStore.COL_THUMBNAIL)
        
        # Setup the drag and drop
        self.drag_dest_set (gtk.DEST_DEFAULT_ALL, (), gtk.gdk.ACTION_COPY)
        targets = ()
        targets = gtk.target_list_add_image_targets (targets, DRAG_IMAGE, False)
        targets = gtk.target_list_add_uri_targets (targets, DRAG_URI)
        self.drag_dest_set_target_list (targets)

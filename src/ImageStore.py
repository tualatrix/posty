import gobject, gtk

# Column indexes
(COL_FILENAME, # The filename of an image (can be None)
 COL_IMAGE, # The image data (if filename is None)
 COL_PREVIEW, # A 512x512 preview of the image
 COL_THUMBNAIL, # A 64x64 thumbnail of the image
 COL_TITLE, # The image title
 COL_DESCRIPTION, # The image description
 COL_TAGS, # A space deliminated list of tags for the image
 COL_SET # An iterator point to the set to put the photo in
 ) = range (0, 8)

class ImageStore (gtk.ListStore):
    def __init__(self):
        gtk.ListStore.__init__(self, gobject.TYPE_STRING, # COL_FILENAME
                               gtk.gdk.Pixbuf, # COL_IMAGE
                               gtk.gdk.Pixbuf, # COL_PREVIEW
                               gtk.gdk.Pixbuf,  #COL_THUMBNAIL
                               gobject.TYPE_STRING, # COL_TITLE
                               gobject.TYPE_STRING, # COL_DESCRIPTION
                               gobject.TYPE_STRING, # COL_TAGS
                               gtk.TreeIter) # COL_SET

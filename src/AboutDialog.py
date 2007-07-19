import gtk

class AboutDialog(gtk.AboutDialog):
    def __init__(self):
        gtk.AboutDialog.__init__(self)
        self.set_name(_('Flickr Uploader'))
        self.set_copyright(u'Copyright \u00A9 2006 Ross Burton')
        self.set_authors(('Ross Burton <ross@burtonini.com>',))
        self.set_website('http://burtonini.com/')
        self.set_logo_icon_name('postr')

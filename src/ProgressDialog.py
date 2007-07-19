import gtk

class ProgressDialog(gtk.Dialog):
    def __init__(self):
        gtk.Dialog.__init__(self, title="", flags=gtk.DIALOG_NO_SEPARATOR)
        self.set_resizable(False)
        self.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

        vbox = gtk.VBox(False, 8)
        vbox.set_border_width(8)
        self.vbox.add(vbox)
        
        hbox = gtk.HBox(False, 8)
        vbox.add (hbox)

        self.thumbnail = gtk.Image()
        hbox.pack_start (self.thumbnail, False, False, 0)

        self.label = gtk.Label()
        self.label.set_alignment (0.0, 0.5)
        hbox.pack_start (self.label, True, True, 0)
        
        self.progress = gtk.ProgressBar()
        vbox.add(self.progress)

        vbox.show_all()
        
if __name__ == "__main__":
    import gobject
    d = ProgressDialog()
    d.thumbnail.set_from_icon_name ("stock_internet", gtk.ICON_SIZE_DIALOG)
    d.label.set_text("Uploading")
    def pulse():
        d.progress.pulse()
        return True
    gobject.timeout_add(200, pulse)
    d.show()
    gtk.main()

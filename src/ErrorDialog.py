import gtk

class ErrorDialog(gtk.MessageDialog):
    def __init__(self, parent=None):
        gtk.MessageDialog.__init__(self, flags=gtk.DIALOG_DESTROY_WITH_PARENT,
                                   type=gtk.MESSAGE_ERROR,
                                   buttons=gtk.BUTTONS_OK,
                                   parent=parent,
                                   message_format="An error occurred")
        self.connect("response", lambda dialog, response: dialog.destroy())

    def set_from_failure (self, failure):
        # TODO: format nicer
        self.format_secondary_text (str (failure.value))


def twisted_error (failure, parent=None):
    # TODO: find out why parent is passed as a GtkWindow but appears here as a
    # GtkVBox.
    dialog = ErrorDialog (parent)
    dialog.set_from_failure (failure)
    dialog.show_all ()

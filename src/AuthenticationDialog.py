import subprocess
import gtk, gconf

def on_url_clicked(button, url):
    """Global LinkButton handler that starts the default GNOME HTTP handler, or
    firefox."""
    client = gconf.client_get_default()
    browser = client.get_string("/desktop/gnome/url-handlers/http/command") or "firefox %s"
    # Because URLs contain & it needs to be quoted
    browser = browser % '"' + url + '"'
    subprocess.Popen(args=browser, shell=True)

class AuthenticationDialog(gtk.Dialog):
    def __init__(self, parent, url):
        gtk.Dialog.__init__(self,
                            title="Flickr Uploader", parent=parent,
                            flags=gtk.DIALOG_NO_SEPARATOR,
                            buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                                     "Continue", gtk.RESPONSE_ACCEPT))
        vbox = gtk.VBox(spacing=8)
        vbox.set_border_width(8)
        
        label = gtk.Label("Postr needs to login to Flickr to upload your photos. "
                          "Please click on the link below to login to Flickr.")
        label.set_line_wrap(True)
        vbox.add(label)

        # gtk.LinkButton is only in 2.10, so use a normal button if it isn't
        # available.
        if hasattr(gtk, "LinkButton"):
            gtk.link_button_set_uri_hook(on_url_clicked)
            button = gtk.LinkButton(url, "Login to Flickr")
        else:
            button = gtk.Button("Login to Flickr")
            button.connect("clicked", on_url_clicked, url)
        vbox.add(button)
        
        self.vbox.add(vbox)
        self.show_all()

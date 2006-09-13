# Postr, a Flickr Uploader
#
# Copyright (C) 2006 Ross Burton <ross@burtonini.com>
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

import threading
import gobject

# A cunning decorator to thread an arbitrary method.  See
# http://www.oreillynet.com/onlamp/blog/2006/07/pygtk_and_threading.html
def threaded(f):
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=f, args=args, kwargs=kwargs)
        t.setDaemon(True)
        t.start()
    wrapper.__name__ = f.__name__
    return wrapper

# An even more cunning decorator to run a method call in the main thread via an
# idle handler.  This could simply wrap the call in gtk.threads_enter()/leave()
# but as those locks are not recursive having lots of idle events is better than
# deadlocking.  Thanks to James Hensbridge for improving this, adding kwargs and
# the return value.
def as_idle(f):
    def wrapper(*args, **kwargs):
        event = threading.Event()
        ret = []
        def task():
            ret.append(f(*args, **kwargs))
            event.set()
            return False
        gobject.idle_add(task)
        event.wait()
        return ret[0]
    wrapper.__name__ = f.__name__
    return wrapper

# -*- encoding: utf-8; mode: python -*-
#
# PyUnique, a pure python reimplementation of unique, a
# single-instance application library.
#
# Copyright © 2010 Karl Mikaelsson <derfian@lysator.liu.se>
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
#
#

import gobject
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gtk import gdk
import time

# Set the glib main loop as the default main loop for dbus
#
DBusGMainLoop(set_as_default=True)

# Default Unique response codes
#
RESPONSE_INVALID = 0
RESPONSE_OK = 1
RESPONSE_CANCEL = 2
RESPONSE_FAIL = 3
RESPONSE_PASSTHROUGH = 4

class UniqueException(Exception):
    """ Base class for Unique exceptions """
    pass

class UniqueBadCommand(UniqueException):
    """ A bad command id was given """
    pass

class UniqueNotRunning(UniqueException):
    """ An instance of UniqueApp isn't running """
    pass

class UniqueDBusObject(dbus.service.Object):
    """ Listener object on the dbus session bus. """
    def __init__(self, bus, path, app):
        dbus.service.Object.__init__(self, bus, path)
        self.app = app

    @dbus.service.method("org.gtk.PyUniqueApp",
                         in_signature = 'is',
                         out_signature = 's')
    def SendMessage(self, command, data):
        self.app.emit('message-received', command, data)
        return "OK"
    
class UniqueApp(gobject.GObject):
    """ Base class for every single instance application."""

    __gproperties__ = {

        'is-running': (gobject.TYPE_BOOLEAN, 'is-running', 'is-running',
                       False,
                       gobject.PARAM_READWRITE | gobject.PARAM_CONSTRUCT),
        'name': (gobject.TYPE_STRING, 'program name', 'program name',
                 None, gobject.PARAM_READWRITE | gobject.PARAM_CONSTRUCT),
        'screen': (gobject.TYPE_OBJECT, 'screen of app', 'screen of app',
                   gobject.PARAM_READWRITE | gobject.PARAM_CONSTRUCT),
        'startup-id': (gobject.TYPE_STRING, 'startup notification id',
                       'startup notification id',
                       None, gobject.PARAM_READWRITE | gobject.PARAM_CONSTRUCT),
        }

    __gsignals__ = {
        'message-received': (gobject.SIGNAL_RUN_LAST |
                             gobject.SIGNAL_NO_RECURSE,
                             gobject.TYPE_INT,        # out: integer
                             (gobject.TYPE_INT,       # in:  command id
                              gobject.TYPE_STRING)),  # in:  command data
        }
    
    # Default commands available to UniqueApp instances. More commands
    # can be added using the add_command method.
    commands = {'INVALID':   0,
                'ACTIVATE': -1,
                'NEW':      -2,
                'OPEN':     -3,
                'CLOSE':    -4}
    
    def __init__(self, name, startup_id=None):
        gobject.GObject.__init__(self)
        
        self._is_running = False
        self._name = name
        self._screen = gdk.screen_get_default()

        # TODO: Find out what the startup_id is meant to be.
        self._startup_id = startup_id
        self.sess_bus = dbus.SessionBus()
        lock = "%s.lock" % name #"org.gtk.PyUnique.lock"

        good_requests = [dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER,
                         dbus.bus.REQUEST_NAME_REPLY_ALREADY_OWNER]

        # Acquire dbus "lock" - I don't want multiple processes
        # starting at once.
        while self.sess_bus.request_name(lock) not in good_requests:
            time.sleep(0.1)

        # So when we've arrived here, we're sure to be the only
        # process executing this. A FIXME would be that this lock is a
        # global lock for all PyUnique applications that hasn't
        # modified the lock string themselves. Perhaps we should
        # incorporate self.name into the locking string?

        try:
            # Try to get the object of the already running UniqueApp
            # instance. If this succeeds, there is another instance
            # running, therefore we can set the is-running property.
            self.running_process = self.sess_bus.get_object(self.props.name,
                                                            "/Factory")
            self.set_property('is-running', True)
        except dbus.DBusException:
            # We got a DBus exception. This means that most likely,
            # noone is listening at the object path. The is-running is
            # left at its default False state.
            self.busname = dbus.service.BusName(self._name, self.sess_bus)
            self.busobj = UniqueDBusObject(self.sess_bus, "/Factory", self)

        self.sess_bus.release_name(lock)

    def is_running(self):
        """ Is another UniqueApp instance running? """
        return self.get_property('is-running')
    
    def send_message(self, command, message):
        """ Send a message to the running UniqueApp instance. """

        # It makes only sense to send messages if there's another
        # process waiting to receive them.
        if not self.get_property('is-running'):
            raise UniqueNotRunning, "Can't send message to nonexistant other instance"
        
        # Validate the command id 
        if not command in self.commands.values():
            raise UniqueBadCommand, "Undefined command"
        
        return self.running_process.SendMessage(command,
                                                message,
                                                dbus_interface="org.gtk.PyUniqueApp")
    
    def add_command(self, command_name, command_id):
        """ Adds command_name as a custom command. You must call
        UniqueApp.add_command() before UniqueApp.send_message() in
        order to use the newly added command."""

        if command_name in self.commands.keys() or \
           command_id in self.commands.values():
            raise UniqueException, "Command ID or name already added"

        self.commands[command_name] = command_id
        
    def add_window(self, window):
        """ Add a window to be watched.. for something. """
        #
        # TODO: Need to figure out this one
        #
        pass

    def watch_window(self, window):
        """ Monitor window for startup notifications... whatever. """
        #
        # TODO: Need to figure out this one
        #
        pass

    def _emit_message_received(self, command, data):
        """ Emit the message-received signal. Called by the DBus
        listener object. """
        self.emit('message-received', command, data)


    #
    # Boilerplate GObject code for mapping properties to instance
    # variables.
    #
        
    def do_get_property(self, prop):
        """ Actual method for getting a property value from an
        instance variable """
        if prop.name == 'is-running':
            return self._is_running
        elif prop.name == 'name':
            return self._name
        elif prop.name == 'screen':
            return self._screen
        elif prop.name == 'startup-id':
            return self._startup_id
        else:
            raise AttributeError, 'unknown property %s' % prop.name

    def do_set_property(self, prop, value):
        """ Actual method for setting a property value to an instance
        variable """
        if prop.name == 'is-running':
            self._is_running = value
        elif prop.name == 'name':
            self._name = value
        elif prop.name == 'screen':
            self._screen = value
        elif prop.name == 'startup-id':
            self._startup_id = value
        else:
            raise AttributeError, 'unknown property %s' % prop.name

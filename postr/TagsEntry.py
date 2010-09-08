# Postr, a Flickr Uploader
#
# Copyright (C) 2009 Francisco Rojas <frojas@alumnos.utalca.cl>
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

import gtk

_USER_POPULAR_TAGS = 200
_HOTS_TAGS = 20
_COL_TAG_NAME = 0

class TagsEntry(gtk.Entry):
    def __init__(self, flickr):
        gtk.Entry.__init__(self)

        self.flickr = flickr

        # Create the completion object
        self.completion = gtk.EntryCompletion()
        self.completion.set_match_func(self.__match_func, None)
        self.completion.connect('match-selected', self.on_completion_match)

        # Assign the completion to the entry
        self.set_completion(self.completion)

        # Use model column _COL_TAG_NAME as the text column
        self.completion.set_text_column(_COL_TAG_NAME)

        self.completion.set_minimum_key_length(1)


        self.completion_model = gtk.ListStore(str)

        self.show_all()

    def on_completion_match(self, completion, model, iter):
        current_text = self.get_text()
        # if more than a word has been typed, we throw away the
        # last one because we want to replace it with the matching word
        # note: the user may have typed only a part of the entire word
        #       and so this step is necessary
        if ' ' in current_text:
            current_text = ' '.join(current_text.split(' ')[:-1])
            # add the matching word
            current_text = '%s %s ' % (current_text, model[iter][_COL_TAG_NAME])
        else:
            current_text = model[iter][_COL_TAG_NAME] +' '

        # set back the whole text
        self.set_text(current_text)
        # move the cursor at the end
        self.set_position(-1)

        return True


    def __match_func(self, completion, key_string, iter, data):
        model = completion.get_model()
        # get the completion strings
        modelstr = model[iter][_COL_TAG_NAME]
        # check if the user has typed in a space char,
        # get the last word and check if it matches something
        if ' ' in key_string:
            last_word = key_string.split(' ')[-1].strip()
            if last_word == '':
                return False
            else:
                return modelstr.lower().startswith(last_word.lower())
        # we have only one word typed
        return modelstr.lower().startswith(key_string.lower())

    def update(self):

        self.completion_model.clear()

        self.flickr.tags_getListUserPopular(user_id=self.flickr.get_nsid(), \
        count=_USER_POPULAR_TAGS).addCallbacks(self.create_completion_model,
        self.twisted_error)

        self.flickr.tags_getHotList(user_id=self.flickr.get_nsid(), count=_HOTS_TAGS)\
        .addCallbacks(self.create_completion_model, self.twisted_error)

    def create_completion_model(self, rsp):
        '''
            Creates a tree model containing the completions.
        '''

        for tag in rsp.getiterator('tag'):
            self.completion_model.set(self.completion_model.append(),
                                    _COL_TAG_NAME,
                                    tag.text)

        self.completion.set_model(self.completion_model)

    def twisted_error(self, failure):
        #TODO: throw a message in a less invasive way
        from ErrorDialog import ErrorDialog
        dialog = ErrorDialog()
        dialog.set_from_failure(failure)
        dialog.show_all()

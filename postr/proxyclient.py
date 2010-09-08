# -*- test-case-name: twisted.web.test.test_webclient -*-

# Copyright (c) 2001-2004 Twisted Matrix Laboratories.
# See LICENSE for details.

#

"""HTTP client.

API Stability: stable
"""

import urlparse, os, types

from twisted.web import http
from twisted.internet import defer, protocol, reactor
from twisted.internet.main import CONNECTION_LOST
from twisted.python import failure
from twisted.python.util import InsensitiveDict
from twisted.web import error

class PartialDownloadError(error.Error):
    """Page was only partially downloaded, we got disconnected in middle.

    The bit that was downloaded is in the response attribute.
    """

class HTTPPageGetter(http.HTTPClient):

    quietLoss = 0
    followRedirect = 1 
    failed = 0

    def connectionMade(self):
        method = getattr(self.factory, 'method', 'GET')
        self.sendCommand(method, self.factory.path)
        self.sendHeader('Host', self.factory.headers.get("host", self.factory.host))
        self.sendHeader('User-Agent', self.factory.agent)
        if self.factory.cookies:
            l=[]
            for cookie, cookval in self.factory.cookies.items():  
                l.append('%s=%s' % (cookie, cookval))
            self.sendHeader('Cookie', '; '.join(l))
        data = getattr(self.factory, 'postdata', None)
        if data is not None:
            self.sendHeader("Content-Length", str(len(data)))
        for (key, value) in self.factory.headers.items():
            if key.lower() != "content-length":
                # we calculated it on our own
                self.sendHeader(key, value)
        self.endHeaders()
        self.headers = {}
        self.writeTheData(data)

    def writeTheData(self, data):
        if data is not None:
            self.transport.write(data)

    def handleHeader(self, key, value):
        key = key.lower()
        l = self.headers[key] = self.headers.get(key, [])
        l.append(value)

    def handleStatus(self, version, status, message):
        self.version, self.status, self.message = version, status, message
        self.factory.gotStatus(version, status, message)

    def handleEndHeaders(self):
        self.factory.gotHeaders(self.headers)
        m = getattr(self, 'handleStatus_'+self.status, self.handleStatusDefault)
        m()

    def handleStatus_200(self):
        pass

    handleStatus_201 = lambda self: self.handleStatus_200()
    handleStatus_202 = lambda self: self.handleStatus_200()

    def handleStatusDefault(self):
        self.failed = 1

    def handleStatus_301(self):
        l = self.headers.get('location')
        if not l:
            self.handleStatusDefault()
            return
        url = l[0]
        if self.followRedirect:
            scheme, host, port, path = \
                _parse(url, defaultPort=self.transport.getPeer().port)
            self.factory.setURL(url)
    
            if self.factory.scheme == 'https':
                from twisted.internet import ssl
                contextFactory = ssl.ClientContextFactory()
                reactor.connectSSL(self.factory.host, self.factory.port, 
                                   self.factory, contextFactory)
            else:
                reactor.connectTCP(self.factory.host, self.factory.port, 
                                   self.factory)
        else:
            self.handleStatusDefault()
            self.factory.noPage(
                failure.Failure(
                    error.PageRedirect(
                        self.status, self.message, location = url)))
        self.quietLoss = 1
        self.transport.loseConnection()

    handleStatus_302 = lambda self: self.handleStatus_301()

    def handleStatus_303(self):
        self.factory.method = 'GET'
        self.handleStatus_301()

    def connectionLost(self, reason):
        if not self.quietLoss:
            http.HTTPClient.connectionLost(self, reason)
            self.factory.noPage(reason)
    
    def handleResponse(self, response):
        if self.quietLoss:
            return
        if self.failed:
            self.factory.noPage(
                failure.Failure(
                    error.Error(
                        self.status, self.message, response)))
        elif self.length != None and self.length != 0:
            self.factory.noPage(failure.Failure(
                PartialDownloadError(self.status, self.message, response)))
        else:
            self.factory.page(response)
        # server might be stupid and not close connection. admittedly
        # the fact we do only one request per connection is also
        # stupid...
        self.transport.loseConnection()

    def timeout(self):
        self.quietLoss = True
        self.transport.loseConnection()
        self.factory.noPage(defer.TimeoutError("Getting %s took longer than %s seconds." % (self.factory.url, self.factory.timeout)))


class HTTPPageDownloader(HTTPPageGetter):

    transmittingPage = 0

    def handleStatus_200(self, partialContent=0):
        HTTPPageGetter.handleStatus_200(self)
        self.transmittingPage = 1
        self.factory.pageStart(partialContent)

    def handleStatus_206(self):
        self.handleStatus_200(partialContent=1)
    
    def handleResponsePart(self, data):
        if self.transmittingPage:
            self.factory.pagePart(data)

    def handleResponseEnd(self):
        if self.transmittingPage:
            self.factory.pageEnd()
            self.transmittingPage = 0
        if self.failed:
            self.factory.noPage(
                failure.Failure(
                    error.Error(
                        self.status, self.message, None)))
            self.transport.loseConnection()


class HTTPClientFactory(protocol.ClientFactory):
    """Download a given URL.

    @type deferred: Deferred
    @ivar deferred: A Deferred that will fire when the content has
          been retrieved. Once this is fired, the ivars `status', `version',
          and `message' will be set.

    @type status: str
    @ivar status: The status of the response.

    @type version: str
    @ivar version: The version of the response.

    @type message: str
    @ivar message: The text message returned with the status.

    @type response_headers: dict
    @ivar response_headers: The headers that were specified in the
          response from the server.
    """

    protocol = HTTPPageGetter

    url = None
    scheme = None
    host = ''
    port = None
    path = None

    def __init__(self, url, method='GET', postdata=None, headers=None,
                 agent="Twisted PageGetter", timeout=0, cookies=None,
                 followRedirect=1, proxy=None):
        self.protocol.followRedirect = followRedirect
        self.timeout = timeout
        self.agent = agent
        self.proxy = proxy

        if cookies is None:
            cookies = {}
        self.cookies = cookies
        if headers is not None:
            self.headers = InsensitiveDict(headers)
        else:
            self.headers = InsensitiveDict()
        if postdata is not None:
            self.headers.setdefault('Content-Length', len(postdata))
            # just in case a broken http/1.1 decides to keep connection alive
            self.headers.setdefault("connection", "close")
        self.postdata = postdata
        self.method = method

        self.setURL(url)

        self.waiting = 1
        self.deferred = defer.Deferred()
        self.response_headers = None

    def __repr__(self):
        return "<%s: %s>" % (self.__class__.__name__, self.url)
    
    def setURL(self, url):
        self.url = url
        scheme, host, port, path = _parse(url)
        if scheme and host:
            self.scheme = scheme
            self.host = host
            self.port = port
        if self.proxy:
            self.path = "%s://%s:%s%s" % (self.scheme,  
                                          self.host,  
                                          self.port,  
                                          path)
        else:
            self.path = path

    def buildProtocol(self, addr):
        p = protocol.ClientFactory.buildProtocol(self, addr)
        if self.timeout:
            timeoutCall = reactor.callLater(self.timeout, p.timeout)
            self.deferred.addBoth(self._cancelTimeout, timeoutCall)
        return p

    def _cancelTimeout(self, result, timeoutCall):
        if timeoutCall.active():
            timeoutCall.cancel()
        return result

    def gotHeaders(self, headers):
        self.response_headers = headers
        if headers.has_key('set-cookie'):
            for cookie in headers['set-cookie']:
                cookparts = cookie.split(';')
                cook = cookparts[0]
                cook.lstrip()
                k, v = cook.split('=', 1)
                self.cookies[k.lstrip()] = v.lstrip()

    def gotStatus(self, version, status, message):
        self.version, self.status, self.message = version, status, message

    def page(self, page):
        if self.waiting:
            self.waiting = 0
            self.deferred.callback(page)

    def noPage(self, reason):
        if self.waiting:
            self.waiting = 0
            self.deferred.errback(reason)

    def clientConnectionFailed(self, _, reason):
        if self.waiting:
            self.waiting = 0
            self.deferred.errback(reason)


class HTTPDownloader(HTTPClientFactory):
    """Download to a file."""
    
    protocol = HTTPPageDownloader
    value = None

    def __init__(self, url, fileOrName,
                 method='GET', postdata=None, headers=None,
                 agent="Twisted client", supportPartial=0):
        self.requestedPartial = 0
        if isinstance(fileOrName, types.StringTypes):
            self.fileName = fileOrName
            self.file = None
            if supportPartial and os.path.exists(self.fileName):
                fileLength = os.path.getsize(self.fileName)
                if fileLength:
                    self.requestedPartial = fileLength
                    if headers == None:
                        headers = {}
                    headers["range"] = "bytes=%d-" % fileLength
        else:
            self.file = fileOrName
        HTTPClientFactory.__init__(self, url, method=method, postdata=postdata, headers=headers, agent=agent)
        self.deferred = defer.Deferred()
        self.waiting = 1

    def gotHeaders(self, headers):
        if self.requestedPartial:
            contentRange = headers.get("content-range", None)
            if not contentRange:
                # server doesn't support partial requests, oh well
                self.requestedPartial = 0 
                return
            start, end, realLength = http.parseContentRange(contentRange[0])
            if start != self.requestedPartial:
                # server is acting wierdly
                self.requestedPartial = 0

    def openFile(self, partialContent):
        if partialContent:
            file = open(self.fileName, 'rb+')
            file.seek(0, 2)
        else:
            file = open(self.fileName, 'wb')
        return file

    def pageStart(self, partialContent):
        """Called on page download start.

        @param partialContent: tells us if the download is partial download we requested.
        """
        if partialContent and not self.requestedPartial:
            raise ValueError, "we shouldn't get partial content response if we didn't want it!"
        if self.waiting:
            self.waiting = 0
            try:
                if not self.file:
                    self.file = self.openFile(partialContent)
            except IOError:
                #raise
                self.deferred.errback(failure.Failure())

    def pagePart(self, data):
        if not self.file:
            return
        try:
            self.file.write(data)
        except IOError:
            #raise
            self.file = None
            self.deferred.errback(failure.Failure())

    def pageEnd(self):
        if not self.file:
            return
        try:
            self.file.close()
        except IOError:
            self.deferred.errback(failure.Failure())
            return
        self.deferred.callback(self.value)


def _parse(url, defaultPort=None):
    url = url.strip()
    parsed = urlparse.urlparse(url)
    scheme = parsed[0]
    path = urlparse.urlunparse(('','')+parsed[2:])
    if defaultPort is None:
        if scheme == 'https':
            defaultPort = 443
        else:
            defaultPort = 80
    host, port = parsed[1], defaultPort
    if ':' in host:
        host, port = host.split(':')
        port = int(port)
    if path == "":
        path = "/"
    return scheme, host, port, path


def getPage(url, contextFactory=None, proxy=None, *args, **kwargs):
    """
    This method has been refactored to _makeDeferredRequest, for more
    information, see the comment there.
    """
    return _makeDeferredRequest(url, contextFactory=contextFactory,
                                proxy=proxy, *args, **kwargs)


def downloadPage(url, file, contextFactory=None, *args, **kwargs):
    """Download a web page to a file.

    @param file: path to file on filesystem, or file-like object.
    
    See HTTPDownloader to see what extra args can be passed.
    """
    scheme, host, port, path = _parse(url)
    factory = HTTPDownloader(url, file, *args, **kwargs)
    if scheme == 'https':
        from twisted.internet import ssl
        if contextFactory is None:
            contextFactory = ssl.ClientContextFactory()
        reactor.connectSSL(host, port, factory, contextFactory)
    else:
        reactor.connectTCP(host, port, factory)
    return factory.deferred

( EXTRA_STEP_SET_ID,
  EXTRA_STEP_GROUPS,
  EXTRA_STEP_LICENSE,
  EXTRA_STEP_NEW_SET,
  EXTRA_STEP_NUM_STEPS ) = range(5)

EXTRA_STEP_FRACTION = 0.04

class UploadProgressTracker(object):
    """
    This object takes a gtk.ProgressBar object as a parameter
    and appropriately calls progress.set_fraction() as more
    data gets written to the pipe.
    """
    def __init__(self, progress):
        self._progress = progress
        self._write_size = 1
        self._write_progress = 0
        self._extra_step_progress = 0

    def set_write_size(self, size):
        """
        Resets the progress count and records the next image's size
        """
        self._extra_step_progress = 0
        self._write_progress = 0
        self._write_size = size

    def _onDataWritten(self, size):
        """ increments the write_progress """
        self._write_progress += size
        self._update_progress()

    def _onConnectionLost(self):
        """ connection lost, same as done writing """
        self._write_progress = 0
        self._write_size = 1
        self._update_progress()

    def _onWriteDone(self):
        """ done writing, zero out progress """
        self._update_progress()

    def complete_extra_step(self, step):
        self._extra_step_progress += EXTRA_STEP_FRACTION

    def _update_progress(self):
        """ updates the progress bar, capping at 100% """
        new_fraction = min(float(self._write_progress) / float(self._write_size),
                           1)
        new_fraction *= (1 - EXTRA_STEP_NUM_STEPS * EXTRA_STEP_FRACTION)
        new_fraction += self._extra_step_progress
        self._progress.set_fraction(new_fraction)

    def wrap_writeSomeData(self, func):
        """
        the horrible decorator to wrap
        twisted.internet.tcp.Connection's implementation of writeSomeData
        standard conventions fd->write return value conventions of
        0 -> done, CONNECTION_LOST -> connection lost, N -> N bytes written
        """
        def inner_writeSomeData(data):
            size = func(data)
            if size == 0:
                self._onWriteDone()
            elif size == CONNECTION_LOST:
                self._onConnectionLost()
            else:
                self._onDataWritten(size)
            return size
        return inner_writeSomeData

class UploadHTTPPageGetter(HTTPPageGetter):
    """
    Subclass of HTTPPageGetter with one gruesome hack.
    Looking at the twisted.internet.tcp.Connection class (which
    this class subclasses) the actual data gets put on the wire
    on writeSomeData.
    http://twistedmatrix.com/documents/current/api/twisted.internet.tcp.Connection.html#writeSomeData
    Since twisted is so abstracted out and simple, we never really
    see the calls of self.transport.writeSomeData, but we obviously
    know it is getting called.  This happens in response to a call to
    self.transport.write.  So we can ensure that writeSomeData is wrapped
    when write is called.
    """
    def set_progress_tracker(self, progress_tracker):
        self._progress_tracker = progress_tracker

    def writeTheData(self, data):
        if data is not None:
            if self._progress_tracker:
                if not hasattr(self.transport, '__has_wrapped_writeSomeData'):
                    self.transport.writeSomeData = self._progress_tracker.wrap_writeSomeData(self.transport.writeSomeData)
                    self.transport.__has_wrapped_writeSomeData = True
                self._progress_tracker.set_write_size(len(data))
            self.transport.write(data)

class UploadHTTPClientFactory(HTTPClientFactory):
    """
    Subclass of HTTPClientFactory that contains a method
    set_progress_tracker that allows the user to specify
    an UploadProgressTracker object to display the uploads
    send percentage.
    """
    protocol = UploadHTTPPageGetter
    _progress_tracker = None

    def __init__(self, *args, **kwargs):
        HTTPClientFactory.__init__(self, *args, **kwargs)

    def buildProtocol(self, addr):
        p = HTTPClientFactory.buildProtocol(self, addr)
        if self._progress_tracker:
            p.set_progress_tracker(self._progress_tracker)
        return p

    def set_progress_tracker(self, progress_tracker):
        self._progress_tracker = progress_tracker
    
def upload(url, contextFactory=None, proxy=None,
           progress_tracker=None, *args, **kwargs):
    """
    This is a horrible hacked version of getPage.  After
    this method overrides the client_factory_class to
    UploadHTTPClientFactory, which has the method 'set_progress_tracker'
    that allows for tracking the progress of the upload.
    """
    return _makeDeferredRequest(url, contextFactory=contextFactory,
                                progress_tracker=progress_tracker,
                                clientFactoryClass=UploadHTTPClientFactory,
                                proxy=proxy, *args, **kwargs)


def _makeDeferredRequest(url, contextFactory=None, proxy=None,
                         progress_tracker=None,
                         clientFactoryClass=None,
                         *args, **kwargs):
    """Download a web page as a string.

    Download a page. Return a deferred, which will callback with a
    page (as a string) or errback with a description of the error.

    See HTTPClientFactory to see what extra args can be passed.
    """
    if proxy:
        scheme, host, port, path = _parse(proxy)
        kwargs['proxy'] = proxy
    else:
        scheme, host, port, path = _parse(url)

    if not clientFactoryClass:
        clientFactoryClass = HTTPClientFactory
    factory = clientFactoryClass(url, *args, **kwargs)

    if progress_tracker is not None and hasattr(factory, 'set_progress_tracker'):
        factory.set_progress_tracker(progress_tracker)

    if scheme == 'https':
        from twisted.internet import ssl
        if contextFactory is None:
            contextFactory = ssl.ClientContextFactory()
        reactor.connectSSL(host, port, factory, contextFactory)
    else:
        reactor.connectTCP(host, port, factory)
    return factory.deferred

import sys
import os
import fcntl
import json
import struct
from select import select
__metaclass__ = type

PY2 = sys.version_info < (3,)


def nonblocking_fd(fd):
    if hasattr(fd, 'fileno'):
        fd = fd.fileno()
    #fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)
    return fd


class MessageReader:
    """Read whole JSON messages from a fd using a chunked protocol."""
    def __init__(self, ioloop, fd, on_message, errback):
        self.loop = ioloop
        self.fd = nonblocking_fd(fd)
        self.callback = on_message
        self.errback = errback
        self.buf = b''
        self.need = 4
        self.msgsize = None

    def on_data(self):
        chunk = os.read(self.fd, max(1, self.need - len(self.buf)))
        if not chunk:
            self.errback(IOError('Unexpected EOF on stream'))
            return
        self.buf += chunk
        self.loop.want_read(self.fd, self.on_data)
        self._check()

    def _check(self):
        """Check if the message size has been reached."""
        while self.running and len(self.buf) >= self.need:
            chunk = self.buf[:self.need]
            self.buf = self.buf[self.need:]
            if self.msgsize is None:
                (self.msgsize,) = struct.unpack('!L', chunk)
                self.need = self.msgsize
            else:
                self.msgsize = None
                self.need = 4
                if not PY2:
                    chunk = chunk.decode('ascii')
                try:
                    decoded = json.loads(chunk)
                except ValueError as e:
                    self.errback(e)
                    return
                else:
                    self.callback(decoded)

    def start(self):
        self.running = True
        self.loop.want_read(self.fd, self.on_data)

    def stop(self):
        self.running = False
        self.loop.abort_read(self.fd)


class MessageWriter:
    def __init__(self, ioloop, fd):
        self.loop = ioloop
        self.fd = nonblocking_fd(fd)
        self.queue = []

    def write(self, msg):
        data = json.dumps(msg).encode('ascii')
        self.queue.append(struct.pack('!L', len(data)) + data)
        self.loop.want_write(self.fd, self.on_write)

    def on_write(self):
        if not self.queue:
            return
        written = os.write(self.fd, self.queue[0])
        b = self.queue[0] = self.queue[0][written:]
        if not b:
            self.queue.pop(0)
        if self.queue:
            self.loop.want_write(self.fd, self.on_write)


class IOLoop:
    """An IO loop allowing the servicing of multiple tunnels with one thread.

    There are many event loops available in Python; this one is particularly
    crude, but avoids introducing another dependency.

    """
    def __init__(self):
        self.read = {}
        self.write = {}
        self.err = {}
        self.result = None

    def want_write(self, fd, callback):
        self.write[fd] = callback

    def want_read(self, fd, callback):
        self.read[fd] = callback

    def abort_read(self, fd):
        self.read.pop(fd, None)

    def step(self):
        rfds = list(self.read)
        wfds = list(self.write)
        rs, ws, xs = select(rfds, wfds, rfds + wfds)
        for r in rs:
            self.read.pop(r)()
        for w in ws:
            self.write.pop(w)()
        # TODO: handle xs

    def reader(self, *args, **kwargs):
        return MessageReader(self, *args, **kwargs)

    def writer(self, *args, **kwargs):
        return MessageWriter(self, *args, **kwargs)

    def stop(self, result=None):
        self.running = False
        self.result = result

    def run(self):
        self.result = None
        self.running = True
        while self.running and (self.read or self.write):
            self.step()
        return self.result

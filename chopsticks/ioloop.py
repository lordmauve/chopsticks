from __future__ import print_function
import sys
import os
import fcntl
import json
import struct
from select import select
__metaclass__ = type

PY2 = sys.version_info < (3,)

if PY2:
    bytes = str


def nonblocking_fd(fd):
    if hasattr(fd, 'fileno'):
        fd = fd.fileno()
    fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)
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
            self.errback('Unexpected EOF on stream')
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
                    self.errback(e.args[0])
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
        self.iter = None
        self.chunk = b''

    def _encode(self, msg):
        """Encode the given message."""
        data = json.dumps(msg).encode('ascii')
        return struct.pack('!L', len(data)) + data

    def write(self, msg):
        self.queue.append(self._encode(msg))
        self.loop.want_write(self.fd, self.on_write)

    def write_iter(self, iterable):
        """Write messages from an iterable to the stream.

        Each message must be JSON-serializable.

        """
        self.queue.append(iterable)

    def on_write(self):
        if not self.queue:
            return
        try:
            written = os.write(self.fd, self.queue[0])
        except OSError:
            return
        b = self.queue[0] = self.queue[0][written:]
        if not b:
            self.queue.pop(0)
            while True:  # may have to loop through empty iterables
                if self.iter:
                    try:
                        msg = next(self.iter)
                    except StopIteration:
                        self.iter = None
                    else:
                        self.queue.insert(0, self._encode(msg))
                        break
                if not self.queue:
                    return
                if isinstance(self.queue[0], bytes):
                    break
                self.iter = self.queue.pop(0)
        self.loop.want_write(self.fd, self.on_write)


class StderrReader:
    """Echo stderr to the console, prefixed by hostname."""
    def __init__(self, ioloop, fd, host):
        self.loop = ioloop
        self.fd = nonblocking_fd(fd)
        self.host = host
        self.buf = b''
        self.loop.want_read(self.fd, self.on_data)

    def on_data(self):
        chunk = os.read(self.fd, 512)
        if not chunk:
            self._flush()
            return
        self.buf += chunk
        self.loop.want_read(self.fd, self.on_data)
        self._check()

    def println(self, l):
        if not PY2:
            l = l.decode('utf8')
        if sys.stderr.isatty():
            fmt = '\x1b[31m[{host}]\x1b[0m {l}'
        else:
            fmt = '[{host}] {l}'
        msg = fmt.format(host=self.host, l=l)
        print(msg, file=sys.stderr)

    def _check(self):
        if b'\n' in self.buf:
            lines = self.buf.split(b'\n')
            self.buf = lines.pop()
            for l in lines:
                self.println(l)

    def _flush(self):
        """Flush the buffer."""
        if self.buf:
            self.println(self.buf)
            self.buf = b''

    def stop(self):
        self.loop.abort_read(self.fd)
        self._flush()

    def __del__(self):
        self.stop()


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
        self.running = False
        self.breakr, self.breakw = os.pipe()

    def want_write(self, fd, callback):
        self.write[fd] = callback
        self.break_select()

    def want_read(self, fd, callback):
        self.read[fd] = callback
        self.break_select()

    def abort_read(self, fd):
        self.read.pop(fd, None)
        self.break_select()

    def break_select(self):
        """Cause the select.select() to break to pick up new fds.

        This is done by including a pipe in the fds passed to select, to which
        we can write. Writing to this pipe will cause select to return early.
        The bytes written are discarded.

        """
        os.write(self.breakw, b'x')

    def step(self):
        rfds = list(self.read) + [self.breakr]
        wfds = list(self.write)
        rs, ws, xs = select(rfds, wfds, rfds + wfds)
        if self.breakr in rs:
            rs.remove(self.breakr)
            os.read(self.breakr, 512)
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

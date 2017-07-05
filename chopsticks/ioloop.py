from __future__ import print_function
import sys
import os
import fcntl
import json
import struct
import weakref
from threading import RLock
from select import select

__metaclass__ = type

PY2 = sys.version_info < (3,)


if PY2:
    bytes = str
    import cPickle as pickle
else:
    import pickle
    unicode = str


def nonblocking_fd(fd):
    if hasattr(fd, 'fileno'):
        fd = fd.fileno()
    fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)
    return fd


HEADER = struct.Struct('!LLbb')
SZ = struct.Struct('!I')

MSG_JSON = 0
MSG_BYTES = 1
MSG_PACK = 2


class MessageReader:
    """Read whole JSON messages from a fd using a chunked protocol."""
    def __init__(self, ioloop, fd, tunnel):
        self.loop = ioloop
        self.fd = nonblocking_fd(fd)
        self.tunnel = weakref.ref(tunnel)
        self.buf = b''
        self.need = HEADER.size
        self.msgsize = None

    @property
    def callback(self):
        tun = self.tunnel()
        if tun:
            return tun.on_message
        return self._abort

    @property
    def errback(self):
        tun = self.tunnel()
        if tun:
            return tun.on_error
        return self._abort

    def _abort(self, *args):
        self.stop()

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
                self.msgsize, self.req_id, self.op, self.fmt = HEADER.unpack(chunk)
                self.need = self.msgsize
            else:
                self.msgsize = None
                self.need = HEADER.size
                if self.fmt == MSG_JSON:
                    if not PY2:
                        chunk = chunk.decode('ascii')
                    try:
                        data = json.loads(chunk)
                    except ValueError as e:
                        self.errback(e.args[0])
                        return
                else:
                    data = chunk
                self.callback((self.op, self.req_id, data))

    def start(self):
        self.running = True
        self.loop.want_read(self.fd, self.on_data)

    def stop(self):
        self.running = False
        self.loop.abort_read(self.fd)


def bsz(seq):
    """Encode the length of a sequence as a big-endian 4-byte unsigned int."""
    return SZ.pack(len(seq))


def pencode(obj):
    """Tiny binary JSON struct encoder.

    We use this in preference to JSON primarily because it can handle the
    difference between bytes and unicode strings, which is much more efficient
    than encoding bytes-as-base64-in-JSON.

    """
    out = []
    _pencode(obj, out)
    return b''.join(out)


def _pencode(obj, out):
    """Inner function for encoding of structures."""
    if isinstance(obj, bytes):
        out.extend([b'b', bsz(obj), obj])
    elif isinstance(obj, unicode):
        bs = obj.encode('utf8')
        out.extend([b's', bsz(bs), bs])
    elif isinstance(obj, bool):
        out.extend([b'1', b't' if obj else b'f'])
    elif isinstance(obj, int):
        bs = str(int(obj)).encode('ascii')
        out.extend([b'i', bsz(bs), bs])
    elif isinstance(obj, (tuple, list)):
        code = b'l' if isinstance(obj, list) else b't'
        out.extend([code, bsz(obj)])
        for item in obj:
            _pencode(item, out)
    elif isinstance(obj, dict):
        out.extend([b'd', bsz(obj)])
        for k in obj:
            if isinstance(k, str):
                if PY2:
                    kbs = str(k)
                else:
                    kbs = str(k).encode('utf8')
                out.extend([b'k', bsz(kbs), kbs])
            else:
                _pencode(k, out)
            _pencode(obj[k], out)
    elif obj is None:
        out.append(b'n')
    else:
        raise ValueError('Unserialisable type %s' % type(obj))


class MessageWriter:
    def __init__(self, ioloop, fd):
        self.loop = ioloop
        self.fd = nonblocking_fd(fd)
        self.queue = []
        self.iter = None
        self.chunk = b''

    def _encode(self, op, req_id, data):
        """Encode the given message."""
        if isinstance(data, dict):
            data = pencode(data)
            fmt = MSG_PACK
        else:
            fmt = MSG_BYTES

        return HEADER.pack(len(data), req_id, op, fmt) + data

    def write(self, op, req_id, data):
        self.write_raw(self._encode(op, req_id, data))

    def write_raw(self, bytes):
        """Write a byte string to the fd."""
        self.queue.append(bytes)
        self.loop.want_write(self.fd, self.on_write)

    def write_iter(self, iterable):
        """Write messages from an iterable to the stream.

        Each message must be JSON-serializable.

        """
        self.queue.append(iterable)
        self.loop.want_write(self.fd, self.on_write)

    def on_write(self):
        if not self.queue:
            return
        try:
            written = os.write(self.fd, self.queue[0])
        except OSError:
            # TODO: handle errors properly
            import traceback
            traceback.print_exc()
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
                        self.queue.insert(0, self._encode(*msg))
                        break
                if not self.queue:
                    return
                if isinstance(self.queue[0], bytes):
                    break
                self.iter = self.queue.pop(0)
        self.loop.want_write(self.fd, self.on_write)

    def stop(self):
        self.loop.abort_write(self.fd)
        del self.queue[:]


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

        # Maintain a lock so that only one thread can be running the loop
        # at once. This makes the loop re-entrant (but the way the loop is
        # called is not yet threadsafe).
        self.lock = RLock()

        # Hold a reference to os functions we need in shutting down
        self.os_write = os.write
        self.os_read = os.read

    def want_write(self, fd, callback):
        self.write[fd] = callback
        self.break_select()

    def want_read(self, fd, callback):
        self.read[fd] = callback
        self.break_select()

    def abort_read(self, fd):
        if self.read.pop(fd, None) is not None:
            self.break_select()

    def abort_write(self, fd):
        if self.write.pop(fd, None) is not None:
            self.break_select()

    def break_select(self):
        """Cause the select.select() to break to pick up new fds.

        This is done by including a pipe in the fds passed to select, to which
        we can write. Writing to this pipe will cause select to return early.
        The bytes written are discarded.

        """
        if self.running:
            self.os_write(self.breakw, b'x')

    def step(self):
        rfds = list(self.read) + [self.breakr]
        wfds = list(self.write)
        rs, ws, xs = select(rfds, wfds, rfds + wfds)
        if self.breakr in rs:
            rs.remove(self.breakr)
            self.os_read(self.breakr, 512)
        for x in xs:
            self.write.pop(x, None)
            reader = self.read.pop(x, None)
            if reader:
                reader.errback('Error on stream')
        for r in rs:
            self.read.pop(r)()
        for w in ws:
            self.write.pop(w)()

    def reader(self, *args, **kwargs):
        return MessageReader(self, *args, **kwargs)

    def writer(self, *args, **kwargs):
        return MessageWriter(self, *args, **kwargs)

    def stop(self, result=None):
        self.running = False
        self.result = result

    def run(self):
        with self.lock:
            self.result = None
            self.running = True
            while self.running and (self.read or self.write):
                self.step()
        return self.result

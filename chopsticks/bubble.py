from __future__ import print_function
import sys
sys.path = [p for p in sys.path if p.startswith('/')]
__name__ = '__bubble__'
sys.modules[__name__] = sys.modules.pop('__main__')


def debug(msg):
    print(msg, file=sys.stderr)

# Reshuffle fds so that we can't break our transport by printing to stdout
import os
infd = os.dup(0)
outfd = os.dup(1)
inpipe = os.fdopen(infd, 'rb')
outpipe = os.fdopen(outfd, 'wb', 0)
sys.stdin.close()
sys.stdin = open(os.devnull, 'r')
sys.stdout.close()
sys.stdout = open(os.devnull, 'w')

PY2 = sys.version_info < (3,)
PY3 = not PY2
import threading
if PY2:
    __metaclass__ = type
    from Queue import Queue
    import cPickle as pickle

    def exec_(_code_, _globs_=None, _locs_=None):
        """Execute code in a namespace."""
        if _globs_ is None:
            frame = sys._getframe(1)
            _globs_ = frame.f_globals
            if _locs_ is None:
                _locs_ = frame.f_locals
            del frame
        elif _locs_ is None:
            _locs_ = _globs_
        exec("""exec _code_ in _globs_, _locs_""")
    range = xrange
else:
    from queue import Queue
    import pickle
    exec_ = getattr(__builtins__, 'exec')
from imp import is_builtin
import time
import json
import struct
import imp
from collections import namedtuple
import signal
from hashlib import sha1
import traceback
from base64 import b64decode
import tempfile
import codecs


utf8_decode = codecs.getdecoder('utf8')

outqueue = Queue(maxsize=10)
tasks = Queue()
done = object()

running = True

Imp = namedtuple('Imp', 'exists is_pkg file source')
PREFIX = 'chopsticks://'


class Loader:
    # Imports that don't succeed after this amount of time will time out
    # This can help crash a remote process when the controller hangs, thus
    # breaking the deadlock.
    TIMEOUT = 5  # seconds

    cache = {}
    lock = threading.RLock()
    ev = threading.Condition(lock)

    def __init__(self, path):
        if not path.startswith(PREFIX):
            raise ImportError()
        self.path = path

    @classmethod
    def on_receive(cls, mod, imp):
        with cls.lock:
            if isinstance(mod, list):
                mod = tuple(mod)
            cls.cache[mod] = imp
            cls.ev.notifyAll()

    def _raw_get(self, fullname):
        with self.lock:
            if fullname in self.cache:
                return self.cache[fullname]
            send_msg(OP_IMP, 0, {'imp': fullname})
            start = time.time()
            self.ev.wait(timeout=self.TIMEOUT)
            delay = time.time() - start
            if delay >= self.TIMEOUT:
                raise IOError(
                    'Timed out after %ds waiting for import %r'
                    % (self.TIMEOUT, fullname)
                )
            try:
                imp = self.cache[fullname]
            except KeyError:
                raise IOError(
                    'Did not find %s in %s' % (fullname, self.cache)
                )
        return imp

    def get(self, fullname):
        if isinstance(fullname, str) and is_builtin(fullname) != 0:
            raise ImportError()
        imp = self._raw_get(fullname)
        if not imp.exists:
            raise ImportError()
        return imp

    def find_module(self, fullname, path=None):
        try:
            self.get(fullname)
        except ImportError:
            return None
        return self

    def load_module(self, fullname):
        m = self.get(fullname)
        modname = fullname
        if fullname == '__main__':
            # Special-case __main__ so as not to execute
            # if __name__ == '__main__' blocks
            modname = '__chopsticks_main__'
        mod = sys.modules.setdefault(modname, imp.new_module(modname))
        mod.__file__ = PREFIX + m.file
        mod.__loader__ = self
        if m.is_pkg:
            modpath = PREFIX + m.file.rsplit('/', 1)[0] + '/'
            mod.__path__ = [modpath]
            mod.__package__ = modname
            #mod.__loader__ = Loader(modpath)
        else:
            mod.__package__ = modname.rpartition('.')[0]
        code = compile(m.source, mod.__file__, 'exec', dont_inherit=True)
        exec(code, mod.__dict__)
        if fullname == '__main__':
            mod.__name__ == '__main__'
            sys.modules[fullname] = mod
        return mod

    def is_package(self, fullname):
        return self.get(fullname).is_pkg

    def get_source(self, fullname):
        return self.get(fullname).source.decode('utf8')

    def get_data(self, path):
        """Get package data from host."""
        mod = self.path.rsplit('/', 2)[-2]
        relpath = path[len(self.path):]
        imp = self.get((mod, relpath))
        return imp.source


sys.path.append(PREFIX)
sys.path_hooks.append(Loader)


def transmit_errors(func):
    def wrapper(req_id, *args, **kwargs):
        try:
            return func(req_id, *args, **kwargs)
        except:
            send_msg(OP_EXC, req_id, {'tb': traceback.format_exc()})
    return wrapper


@transmit_errors
def handle_call_threaded(req_id, data):
    threading.Thread(target=handle_call_thread, args=(req_id, data)).start()


@transmit_errors
def handle_call_thread(req_id, data):
    callable, args, kwargs = pickle.loads(data)
    do_call(req_id, callable, args, kwargs)


@transmit_errors
def handle_call_queued(req_id, data):
    callable, args, kwargs = pickle.loads(data)
    tasks.put((req_id, callable, args, kwargs))


OP_CALL = 0
OP_RET = 1
OP_EXC = 2
OP_IMP = 3
OP_FETCH_BEGIN = 4
OP_FETCH_DATA = 5
OP_FETCH_END = 6
OP_PUT_BEGIN = 7
OP_PUT_DATA = 8
OP_PUT_END = 9
OP_START = 10


# FIXME: handle_call_queued seems to deadlock!
handle_call = handle_call_threaded


@transmit_errors
def handle_fetch(req_id, path):
    """Fetch a file by path."""
    tasks.put((req_id, do_fetch, (req_id, path,)))


def do_fetch(req_id, path):
    """Send chunks of a file to the orchestration host."""
    h = sha1()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(10240)
            if not chunk:
                break
            h.update(chunk)
            send_msg(OP_FETCH_DATA, req_id, chunk)
    return {
        'remote_path': str(os.path.abspath(path)),
        'sha1sum': h.hexdigest(),
    }


@transmit_errors
def do_call(req_id, callable, args=(), kwargs={}):
    ret = callable(*args, **kwargs)
    send_msg(
        OP_RET,
        req_id,
        {
            'ret': ret,
            # 'callable': callable.__module__ + '.' + callable.__name__
        }
    )


def handle_imp(req_id, mod, exists, is_pkg, file, source):
    Loader.on_receive(mod, Imp(exists, is_pkg, file, source))


active_puts = {}


def force_str(s):
    if not isinstance(s, str):
        return s.decode()
    return s


@transmit_errors
def handle_begin_put(req_id, path, mode):
    prev_umask = os.umask(0o077)
    try:
        if path is None:
            f = tempfile.NamedTemporaryFile(delete=False)
            path = wpath = f.name
        else:
            path = force_str(path)
            if os.path.isdir(path):
                raise IOError('%s is a directory' % path)
            wpath = path + '~chopsticks-tmp'
            f = open(wpath, 'wb')
    finally:
        os.umask(prev_umask)
    os.fchmod(f.fileno(), mode)
    active_puts[req_id] = (f, wpath, path, sha1())


@transmit_errors
def handle_put_data(req_id, data):
    try:
        f, wpath, path, cksum = active_puts[req_id]
    except KeyError:
        # Likely we have crashed out already
        return
    try:
        cksum.update(data)
        f.write(data)
    except:
        try:
            os.unlink(wpath)
            f.close()
        except OSError:
            pass
        raise


class ChecksumMismatch(Exception):
    pass


@transmit_errors
def handle_end_put(req_id, sha1sum):
    try:
        f, wpath, path, cksum = active_puts.pop(req_id)
    except KeyError:
        # Likely we have crashed out already
        return
    received = f.tell()
    f.close()
    digest = cksum.hexdigest()
    sha1sum = force_str(sha1sum)
    if digest != sha1sum:
        try:
            os.unlink(wpath)
        except OSError:
            pass
        raise ChecksumMismatch(
            'Checksum failed for transfer %s (%r != %r)' %
            (path, digest, sha1sum)
        )
    if wpath != path:
        os.rename(wpath, path)
    send_msg(
        OP_RET, req_id, {'ret': {
            'remote_path': os.path.abspath(path),
            'sha1sum': digest,
            'size': received
        }}
    )


def handle_start(req_id, host, path, depthlimit):
    sys._chopsticks_host = force_str(host)
    sys._chopsticks_path = [force_str(p) for p in path]
    sys._chopsticks_depthlimit = depthlimit
    send_msg(OP_RET, req_id, {'ret': pickle.HIGHEST_PROTOCOL})


HEADER = struct.Struct('!LLbb')

MSG_JSON = 0
MSG_BYTES = 1
MSG_PACK = 2


SZ = struct.Struct('!I')


class obuf(object):
    def __init__(self, buf):
        self.buf = buf
        self.offset = 0

    def read_size(self):
        v = SZ.unpack_from(self.buf, self.offset)[0]
        self.offset += SZ.size
        return v

    def read_bytes(self, n):
        start = self.offset
        end = self.offset = start + n
        return self.buf[start:end]


def pdecode(buf):
    return _decode(obuf(buf))


def _decode(obuf):
    code = obuf.read_bytes(1)
    if code == b'k':
        code = b'b' if PY2 else b's'

    if code == b'n':
        return None
    elif code == b'b':
        sz = obuf.read_size()
        return obuf.read_bytes(sz)
    elif code == b's':
        sz = obuf.read_size()
        return utf8_decode(obuf.read_bytes(sz))[0]
    elif code == b'1':
        return obuf.read_bytes(1) == b't'
    elif code == b'i':
        sz = obuf.read_size()
        return int(obuf.read_bytes(sz))
    elif code == b'l':
        sz = obuf.read_size()
        return [_decode(obuf) for _ in range(sz)]
    elif code == b't':
        sz = obuf.read_size()
        return tuple(_decode(obuf) for _ in range(sz))
    elif code == b'd':
        sz = obuf.read_size()
        return dict((_decode(obuf), _decode(obuf)) for _ in range(sz))
    else:
        raise ValueError('Unknown pack opcode %r' % code)


def send_msg(op, req_id, data):
    """Send a message to the orchestration host.

    We can send either bytes or JSON-encoded structured data; the opcode will
    determine which.

    """
    if isinstance(data, dict):
        data = json.dumps(data)
        if not PY2:
            data = data.encode('ascii')
        fmt = MSG_JSON
    else:
        fmt = MSG_BYTES

    chunk = HEADER.pack(len(data), req_id, op, fmt) + data
    outqueue.put(chunk)


def read_msg():
    buf = inpipe.read(HEADER.size)
    if not buf:
        return
    (size, req_id, op, fmt) = HEADER.unpack(buf)
    data = inpipe.read(size)
    if fmt == MSG_BYTES:
        obj = {'data': data}
    elif fmt == MSG_JSON:
        if PY3:
            data = data.decode('ascii')
        obj = json.loads(data)
        if PY2:
            obj = dict((str(k), v) for k, v in obj.iteritems())
    elif fmt == MSG_PACK:
        obj = pdecode(data)
    return (req_id, op, obj)


HANDLERS = {
    OP_CALL: handle_call,
    OP_IMP: handle_imp,
    OP_FETCH_BEGIN: handle_fetch,
    OP_PUT_BEGIN: handle_begin_put,
    OP_PUT_DATA: handle_put_data,
    OP_PUT_END: handle_end_put,
    OP_START: handle_start,
}

def reader():
    try:
        while True:
            msg = read_msg()
            if msg is None:
                break
            req_id, op, params = msg
            HANDLERS[op](req_id, **params)
    finally:
        outqueue.put(done)
        tasks.put(done)


def writer():
    while True:
        msg = outqueue.get()
        if msg is done:
            break
        outpipe.write(msg)


for func in (reader, writer):
    threading.Thread(target=func).start()

while True:
    task = tasks.get()
    if task is done:
        break
    do_call(*task)

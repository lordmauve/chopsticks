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
sys.stdin = open(os.devnull, 'rb')
sys.stdout.close()
sys.stdout = open(os.devnull, 'wb')

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
else:
    from queue import Queue
    import pickle
    exec_ = getattr(__builtins__, 'exec')
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

outqueue = Queue(maxsize=10)
tasks = Queue()
done = object()

running = True

Imp = namedtuple('Imp', 'exists is_pkg file source')
PREFIX = 'controller://'


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

    def get(self, fullname):
        with self.lock:
            if fullname in self.cache:
                return self.cache[fullname]
            send_msg(OP_IMP, 0, {'imp': fullname})
            start = time.time()
            while True:
                self.ev.wait(timeout=self.TIMEOUT)
                if time.time() > start + self.TIMEOUT:
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
                    # continue
                else:
                    break
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
    send_msg(
        OP_RET, req_id, {'ret': {
            'remote_path': os.path.abspath(path),
            'sha1sum': h.hexdigest(),
        }}
    )


@transmit_errors
def do_call(req_id, callable, args=(), kwargs={}):
    ret = callable(*args, **kwargs)
    send_msg(OP_RET, req_id, {'ret': ret})


def handle_imp(req_id, mod, exists, is_pkg, file, source):
    source = b64decode(source)
    Loader.on_receive(mod, Imp(exists, is_pkg, file, source))


active_puts = {}


@transmit_errors
def handle_begin_put(req_id, path, mode):
    prev_umask = os.umask(0o077)
    try:
        if path is None:
            f = tempfile.NamedTemporaryFile(delete=False)
            path = wpath = f.name
        else:
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
    f, wpath, path, cksum = active_puts.pop(req_id)
    received = f.tell()
    f.close()
    digest = cksum.hexdigest()
    if digest != sha1sum:
        try:
            os.unlink(wpath)
        except OSError:
            pass
        raise ChecksumMismatch('Checksum failed for transfer %s' % path)
    if wpath != path:
        os.rename(wpath, path)
    send_msg(
        OP_RET, req_id, {'ret': {
            'remote_path': os.path.abspath(path),
            'sha1sum': digest,
            'size': received
        }}
    )


HEADER = struct.Struct('!LLbb')

MSG_JSON = 0
MSG_BYTES = 1
MSG_PCK = 2


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
    return (req_id, op, obj)


HANDLERS = {
    OP_CALL: handle_call,
    OP_IMP: handle_imp,
    OP_FETCH_BEGIN: handle_fetch,
    OP_PUT_BEGIN: handle_begin_put,
    OP_PUT_DATA: handle_put_data,
    OP_PUT_END: handle_end_put
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

send_msg(OP_RET, 0, {'ret': pickle.HIGHEST_PROTOCOL})
while True:
    task = tasks.get()
    if task is done:
        break
    do_call(*task)

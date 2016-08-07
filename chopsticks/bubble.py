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
import json
import struct
import imp
import base64
from collections import namedtuple
import signal
from hashlib import sha1
import traceback

outqueue = Queue(maxsize=10)
tasks = Queue()
done = object()

running = True

Imp = namedtuple('Imp', 'exists is_pkg file source')
PREFIX = 'controller://'


class Loader:
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
            cls.cache[mod] = imp
            cls.ev.notifyAll()

    def get(self, fullname):
        with self.lock:
            if fullname in self.cache:
                return self.cache[fullname]
            outqueue.put({'imp': fullname})
            while True:
                self.ev.wait()
                try:
                    imp = self.cache[fullname]
                except KeyError:
                    continue
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
            mod.__path__ = [PREFIX + m.file]
            mod.__package__ = modname
        else:
            mod.__package__ = modname.rpartition('.')[0]
        exec(compile(m.source, mod.__file__, 'exec'), mod.__dict__)
        if fullname == '__main__':
            mod.__name__ == '__main__'
            sys.modules[fullname] = mod
        return mod

    def is_package(self, fullname):
        return self.get(fullname).is_pkg

    def get_source(self, fullname):
        return self.get(fullname).source


sys.path.append(PREFIX)
sys.path_hooks.append(Loader)


def transmit_errors(func):
    def wrapper(req_id, *args, **kwargs):
        try:
            return func(req_id, *args, **kwargs)
        except:
            outqueue.put({
                'req_id': req_id,
                'tb': traceback.format_exc()
            })
    return wrapper


@transmit_errors
def handle_call_threaded(req_id, params):
    threading.Thread(target=handle_call_thread, args=(req_id, params)).start()


@transmit_errors
def handle_call_thread(req_id, params):
    callable, args, kwargs = pickle.loads(base64.b64decode(params))
    do_call(req_id, callable, args, kwargs)


@transmit_errors
def handle_call_queued(req_id, params):
    callable, args, kwargs = pickle.loads(base64.b64decode(params))
    tasks.put((req_id, callable, args, kwargs))


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
            data = base64.b64encode(chunk)
            if not PY2:
                data = data.decode('ascii')
            outqueue.put({
                'req_id': req_id,
                'data': data
            })
    return {
        'remote_path': os.path.abspath(path),
        'sha1sum': h.hexdigest(),
    }


@transmit_errors
def do_call(req_id, callable, args=(), kwargs={}):
    ret = callable(*args, **kwargs)
    outqueue.put({
        'req_id': req_id,
        'ret': ret,
    })


def handle_imp(mod, exists, is_pkg, file, source):
    Loader.on_receive(mod, Imp(exists, is_pkg, file, source))


active_puts = {}


@transmit_errors
def handle_begin_put(req_id, path, mode):
    prev_umask = os.umask(0o077)
    try:
        if path is None:
            import tempfile
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
    f, wpath, path, cksum = active_puts[req_id]
    try:
        data = base64.b64decode(data)
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
    outqueue.put({
        'req_id': req_id,
        'ret': {
            'remote_path': os.path.abspath(path),
            'sha1sum': digest,
            'size': received
        }
    })


def read_msg():
    buf = inpipe.read(4)
    if not buf:
        return
    (size,) = struct.unpack('!L', buf)
    chunk = inpipe.read(size)
    if PY3:
        chunk = chunk.decode('ascii')
    return json.loads(chunk)


def reader():
    try:
        while True:
            obj = read_msg()
            if not obj:
                return
            op = obj.pop('op')
            handler = globals()['handle_' + op]
            if PY2:
                obj = dict((str(k), v) for k, v in obj.iteritems())
            handler(**obj)
    finally:
        outqueue.put(done)
        tasks.put(done)


def writer():
    while True:
        msg = outqueue.get()
        if msg is done:
            break
        # pickle is unsafe for the return transport
        buf = json.dumps(msg)
        if PY3:
            buf = buf.encode('ascii')
        outpipe.write(struct.pack('!L', len(buf)))
        outpipe.write(buf)


for func in (reader, writer):
    threading.Thread(target=func).start()


while True:
    task = tasks.get()
    if task is done:
        break
    do_call(*task)

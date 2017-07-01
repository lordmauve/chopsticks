from __future__ import print_function
import subprocess
import sys
import os
import os.path
import pkgutil
import threading
import tempfile
import time
from hashlib import sha1
from base64 import b64encode

from . import ioloop
from .serialise_main import prepare_callable


PY2 = sys.version_info < (3,)

if PY2:
    import cPickle as pickle
else:
    import pickle

__metaclass__ = type

# One global loop for all tunnels
loop = ioloop.IOLoop()

# Another thread will output stderr
errloop = ioloop.IOLoop()


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


def start_errloop():
    if errloop.running:  # FIXME: race condition - may be stopping
        return
    t = threading.Thread(target=errloop.run)
    t.setDaemon(True)
    t.start()


class ErrorResult:
    """Indicates an error returned by the remote host.

    Because tracebacks or error types cannot be represented across hosts this
    will simply consist of a message.

    """
    def __init__(self, msg, tb=None):
        self.msg = msg
        if tb:
            self.msg += '\n\n    ' + '\n    '.join(tb.splitlines())

    def __repr__(self):
        return 'ErrorResult(%r)' % self.msg

    __str__ = __repr__
    __unicode__ = __repr__


class RemoteException(Exception):
    """An exception from the remote agent."""

bubble = pkgutil.get_data('chopsticks', 'bubble.py')


class BaseTunnel:
    def __init__(self):
        self.req_id = 0
        self.callbacks = {}
        self.connected = False
        self.pickle_version = pickle.HIGHEST_PROTOCOL

    def __eq__(self, ano):
        return self.host == ano.host

    def __ne__(self, ano):
        return self.host != ano.host

    def __hash__(self):
        return hash(self.host)

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.host)

    def connect(self):
        if self.connected:
            return
        assert self.host, "No host name received"
        self._connect_async(loop.stop)
        self.connected = True
        pickle_version = loop.run()
        self.pickle_version = min(pickle.HIGHEST_PROTOCOL, pickle_version)

    def _connect_async(self, callback):
        """Connect the tunnel."""
        raise NotImplementedError('Subclasses must implement _connect_async()')

    def write_msg(self, op, req_id, data=None, **kwargs):
        """Write one message to the subprocess.

        This uses a chunked JSON protocol.

        """
        if data and kwargs:
            raise TypeError('Can only send kwargs or data')
        self.writer.write(op, req_id, data or kwargs)

    def _next_id(self):
        self.req_id += 1
        return self.req_id

    @staticmethod
    def _read_source(file):
        with open(file, 'rb') as f:
            data = b64encode(f.read())
            if not PY2:
                data = data.decode('ascii')
            return data

    def handle_imp(self, mod):
        key = mod
        fname = None
        if mod == '__main__':
            # Special-case main to find real main module
            main = sys.modules['__main__']
            path = main.__file__
            self.write_msg(
                OP_IMP,
                0,
                mod=mod,
                exists=True,
                is_pkg=False,
                file=os.path.basename(path),
                source=self._read_source(path)
            )
            return
        elif isinstance(mod, list):
            mod, fname = mod
            if not mod:
                mod, fname = fname.split('/', 1)

        stem = mod.replace('.', os.sep)
        paths = [
            (True, os.path.join(stem, '__init__.py')),
            (False, stem + '.py'),
        ]

        for root in sys.path:
            for is_pkg, rel in paths:
                path = os.path.join(root, rel)
                if os.path.exists(path):
                    if fname is not None:
                        path = os.path.join(root, stem, fname)
                        if not os.path.exists(path):
                            break
                        rel = stem + '/' + fname
                        is_pkg = False

                    self.write_msg(
                        OP_IMP,
                        0,
                        mod=key,
                        exists=True,
                        is_pkg=is_pkg,
                        file=rel,
                        source=self._read_source(path)
                    )
                    return
        self.write_msg(
            OP_IMP,
            0,
            mod=key,
            exists=False,
            is_pkg=False,
            file=None,
            source=''
        )

    def _call_callback(self, req_id, *args):
        try:
            cb = self.callbacks.pop(req_id)
        except KeyError:
            raise KeyError(
                'Unknown request ID %d. Last request ID %s. Callbacks: %r'
                % (req_id, self.req_id, self.callbacks)
            )
        else:
            cb(*args)

    def on_message(self, msg):
        """Pump messages until the given ID is received.

        The current thread will be blocked until the response is received.

        """
        op, req_id, data = msg
        if op == OP_EXC:
            error = ErrorResult(
                'Host %r raised exception; traceback follows' % self.host,
                data['tb']
            )
            self._call_callback(req_id, error)
        elif op == OP_IMP:
            self.handle_imp(data['imp'])
        elif op == OP_RET:
            if req_id not in self.callbacks:
                self._warn('response received for unknown req_id %d' % req_id)
                return

            self._call_callback(req_id, data['ret'])
            self.reader.stop()
        elif op == OP_FETCH_DATA:
            if req_id not in self.callbacks:
                self._warn('response received for unknown req_id %d' % req_id)
                return
            self.callbacks[req_id].recv(data)
        else:
            self._warn('Unknown opcode received %r' % op)

    def _warn(self, msg):
        print('%s:' % self.host, msg, file=sys.stderr)

    def call(self, callable, *args, **kwargs):
        """Call the given callable on the remote host.

        The callable must return a value that can be serialised as JSON,
        but there is no such restriction on the parameters.

        """
        self.connect()
        self._call_async(loop.stop, callable, *args, **kwargs)
        ret = loop.run()
        if isinstance(ret, ErrorResult):
            raise RemoteException(ret.msg)
        return ret

    def _call_async(self, on_result, callable, *args, **kwargs):
        id = self._next_id()
        self.callbacks[id] = on_result
        params = prepare_callable(callable, args, kwargs)
        self.reader.start()
        self.write_msg(
            OP_CALL,
            req_id=id,
            data=pickle.dumps(params, self.pickle_version)
        )

    def fetch(self, remote_path, local_path=None):
        """Fetch one file from the remote host.

        If local_path is given, it is the local path to write to. Otherwise,
        a temporary filename will be used.

        This operation supports arbitarily large files (file data is streamed,
        not buffered in memory).

        The return value is a dict containing:

        * ``local_path`` - the local path written to
        * ``remote_path`` - the absolute remote path
        * ``size`` - the number of bytes received
        * ``sha1sum`` - a sha1 checksum of the file data

        """
        self.connect()
        self._fetch_async(loop.stop, remote_path, local_path)
        ret = loop.run()
        if isinstance(ret, ErrorResult):
            raise RemoteException(ret.msg)
        return ret

    def _fetch_async(self, on_result, remote_path, local_path=None):
        id = self._next_id()
        fetch = Fetch(on_result, local_path)
        self.callbacks[id] = fetch
        self.reader.start()
        self.write_msg(
            OP_FETCH_BEGIN,
            req_id=id,
            path=remote_path,
        )

    def put(self, local_path, remote_path=None, mode=0o644):
        """Copy a file to the remote host.

        If `remote_path` is given, it is the remote path to write to.
        Otherwise, a temporary filename will be used.

        `mode` gives is the permission bits of the file to create, or 0o644 if
        unspecified.

        This operation supports arbitarily large files (file data is streamed,
        not buffered in memory).

        The return value is a dict containing:

        * ``remote_path`` - the absolute remote path
        * ``size`` - the number of bytes received
        * ``sha1sum`` - a sha1 checksum of the file data

        """
        self.connect()
        self._put_async(loop.stop, local_path, remote_path, mode)
        ret = loop.run()
        if isinstance(ret, ErrorResult):
            raise RemoteException(ret.msg)
        return ret

    def _put_async(
            self,
            on_result,
            local_path,
            remote_path=None,
            mode=0o644):
        id = self._next_id()
        self.callbacks[id] = on_result
        self.reader.start()
        self.write_msg(
            OP_PUT_BEGIN,
            id,
            path=remote_path,
            mode=mode
        )
        self.writer.write_iter(
            iter_chunks(id, local_path)
        )


def iter_chunks(req_id, path):
    """Iterate over chunks of the given file.

    Yields message suitable for writing to a stream.

    """
    chksum = sha1()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(10240)
            if not chunk:
                yield OP_PUT_END, req_id, {'sha1sum': chksum.hexdigest()}
                break
            chksum.update(chunk)
            yield OP_PUT_DATA, req_id, chunk


class Fetch(object):
    def __init__(self, on_result, local_path=None):
        self.on_result = on_result
        if local_path:
            self.local_path = local_path
            self.file = open(local_path, 'wb')
        else:
            self.file = tempfile.NamedTemporaryFile('wb', delete=False)
            self.local_path = self.file.name
        self.size = 0
        self.chksum = sha1()

    def recv(self, data):
        self.chksum.update(data)
        self.file.write(data)
        self.size += len(data)

    def __call__(self, result):
        self.file.close()
        if not isinstance(result, ErrorResult):
            remote_chksum = result['sha1sum']
            if remote_chksum != self.chksum.hexdigest():
                result = ErrorResult('Fetch failed due to checksum mismatch')
            else:
                result['local_path'] = self.local_path
            result['size'] = self.size

        if isinstance(result, ErrorResult):
            os.unlink(self.local_path)
        self.on_result(result)


class PipeTunnel(BaseTunnel):
    """A tunnel that connects via a pair of unidirectional pipes.

    Subclasses will need to implement ``connect_pipes()`` to create the
    ``self.wpipe`` and ``self.rpipe`` pipe attibutes.

    """

    def _connect_async(self, callback):
        self.connect_pipes()
        self.reader = loop.reader(self.rpipe, self)
        self.writer = loop.writer(self.wpipe)

        # Remote sends a pickle_version with req_id 0
        self.callbacks[0] = callback
        self.reader.start()
        self.writer.write_raw(bubble)

        self.errreader = ioloop.StderrReader(errloop, self.epipe, self.host)
        start_errloop()

    def on_error(self, err):
        err = ErrorResult(err)
        for id in list(self.callbacks):
            self.callbacks.pop(id)(err)

    def close(self):
        if not self.connected:
            return
        self.wpipe.close()  # Terminate child
        self.connected = False  # Assume we'll disconnect successfully

        if self.proc.poll() is not None:
            # subprocess is already dead
            return

        # Send TERM
        self.proc.terminate()

        # Wait for process to shut down cleanly
        timeout = time.time() + 5
        while time.time() < timeout:
            if self.proc.poll() is not None:
                return
            time.sleep(0.01)

        # Process did not shut down cleanly; force kill it
        self.proc.kill()
        self._warn('Timeout expired waiting for pipe to close')

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, trackback):
        self.close()


class SubprocessTunnel(PipeTunnel):
    """A tunnel that connects to a subprocess."""

    #: These arguments are used for bootstrapping Python into out remote agent
    PYTHON_ARGS = [
        '-usS',
        '-c',
        'import sys, os; sys.stdin = os.fdopen(0, \'rb\', 0); ' +
        '__bubble = sys.stdin.read(%d); ' % len(bubble) +
        'exec(compile(__bubble, \'bubble.py\', \'exec\'))'
    ]

    # Paths to the Python 2/3 binary on the remote host
    python2 = '/usr/bin/python2'
    python3 = '/usr/bin/python3'

    def connect_pipes(self):
        self.proc = subprocess.Popen(
            self.cmd_args(),
            bufsize=0,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            preexec_fn=os.setpgrp
        )
        self.wpipe = self.proc.stdin
        self.rpipe = self.proc.stdout
        self.epipe = self.proc.stderr

    def cmd_args(self):
        python = self.python2 if PY2 else self.python3
        return [python] + self.PYTHON_ARGS


class Local(SubprocessTunnel):
    """A tunnel to a subprocess on the same host."""

    def __init__(self, name='localhost'):
        self.host = name
        super(Local, self).__init__()


class Sudo(SubprocessTunnel):
    """A tunnel to a process on the same host, launched with sudo."""

    def __init__(self, user='root', name=None):
        self.user = user
        self.host = name or user + '@localhost'
        super(Sudo, self).__init__()

    def cmd_args(self):
        args = [
            'sudo',
            '--non-interactive',
            '-u', self.user
        ]
        args += super(Sudo, self).cmd_args()
        return args

    def close(self):
        """Close the tunnel.

        Here we override the base class implementation which tries to kill
        the tunnel if it does not shut down in a timely fashion, because we
        cannot kill a root process.

        """
        self.wpipe.close()
        self.proc.wait()


class Docker(SubprocessTunnel):
    """A tunnel connected to a throwaway Docker container."""

    #: For the standard Python docker images, Python is not installed as
    #: /usr/bin/python[23]
    python2 = 'python'
    python3 = 'python3'

    pyver = '{0}.{1}'.format(*sys.version_info)

    def __init__(self, name, image='python:' + pyver, rm=True):
        self.host = name
        self.image = image
        self.rm = rm
        super(Docker, self).__init__()

    def cmd_args(self):
        base = super(Docker, self).cmd_args()
        args = []
        if self.rm:
            args.append('--rm')

        return [
            'docker',
            'run',
            '-i',
            '--name',
            self.host,
        ] + args + [self.image] + base


class SSHTunnel(SubprocessTunnel):
    """A tunnel that connects to a remote host over SSH."""
    def __init__(self, host, user=None, sudo=False):
        self.host = host
        self.user = user
        self.sudo = sudo
        super(SubprocessTunnel, self).__init__()

    def cmd_args(self):
        args = ['ssh', '-o', 'PasswordAuthentication=no']
        if self.user:
            args.extend(['-l', self.user])
        args.append(self.host)
        if self.sudo:
            args.append('sudo')
        args.extend(super(SSHTunnel, self).cmd_args())
        return ['"%s"' % w if ' ' in w else w for w in args]


# An alias, because this is the default tunnel type
Tunnel = SSHTunnel

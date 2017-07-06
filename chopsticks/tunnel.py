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
from contextlib import contextmanager

import chopsticks
from . import ioloop
from .setops import SetOps
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
OP_START = 10

CHOPSTICKS_PREFIX = 'chopsticks://'


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


class DepthLimitExceeded(Exception):
    """The recursive tunnel depth limit was hit."""


bubble = pkgutil.get_data('chopsticks', 'bubble.py')


class BaseTunnel(SetOps):
    HIGHEST_PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL

    def __init__(self):
        self._reset()

    def _reset(self):
        self.req_id = 0
        self.callbacks = {}
        self.connected = False
        self.pickle_version = self.HIGHEST_PICKLE_PROTOCOL

    def __eq__(self, ano):
        return self.host == ano.host

    def __ne__(self, ano):
        return self.host != ano.host

    def __hash__(self):
        return hash(self.host)

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.host)

    def _as_group(self):
        """Tunnels behave like groups of one tunnel."""
        from chopsticks.group import Group
        return Group([self])

    def _run_loop(self):
        """Run the loop, but clean up after crashes."""
        try:
            return loop.run()
        except:
            self.close()
            raise

    def connect(self):
        if self.connected:
            return
        assert self.host, "No host name received"
        self._connect_async(loop.stop)
        res = self._run_loop()
        if isinstance(res, ErrorResult):
            raise RemoteException(res.msg)

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

    @classmethod
    def _read_source(cls, file):
        with open(file, 'rb') as f:
            return f.read()

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
            if root == CHOPSTICKS_PREFIX:
                importer = sys.path_importer_cache[root]
                if fname:
                    req = (mod, fname)
                else:
                    req = mod
                try:
                    imp = importer._raw_get(req)
                except ImportError:
                    continue
                else:
                    self.write_msg(
                        OP_IMP,
                        0,
                        mod=key,
                        exists=imp.exists,
                        is_pkg=imp.is_pkg,
                        file=imp.file,
                        source=imp.source,
                    )
                    return

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

    def _get_callback(self, req_id, data):
        try:
            return self.callbacks[req_id]
        except KeyError:
            raise RuntimeError(
                'response received for unknown req_id %d.' % req_id +
                ' data: %s' % data +
                ' callbacks: %s' % self.callbacks
            )

    def _pop_callback(self, req_id, data):
        cb = self._get_callback(req_id, data)
        del self.callbacks[req_id]
        return cb

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
            self._pop_callback(req_id, data)(error)
        elif op == OP_IMP:
            self.handle_imp(data['imp'])
        elif op == OP_RET:
            self.reader.stop()
            self._pop_callback(req_id, data)(data['ret'])
        elif op == OP_FETCH_DATA:
            self._get_callback(req_id, data).recv(data)
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
        ret = self._run_loop()
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
        ret = self._run_loop()
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
        ret = self._run_loop()
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

    def close():
        """Disconnect the tunnel.

        Note that this will terminate the remote process and any state will
        be lost. This does not destroy the Tunnel object, which can be
        reconnected with :meth:`.connect()`.

        """
        raise NotImplementedError()


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
        if self.connected:
            callback(None)
            return
        try:
            path = sys._chopsticks_path[:]
        except AttributeError:
            path = []
        path.append(self.host)

        if len(path) > chopsticks.DEPTH_LIMIT:
            raise DepthLimitExceeded(
                'Depth limit of %s exceeded at %s' % (
                    chopsticks.DEPTH_LIMIT,
                    ' -> '.join(path)
                )
            )

        self.connect_pipes()
        self.reader = loop.reader(self.rpipe, self)
        self.writer = loop.writer(self.wpipe)

        def wrapped_callback(res):
            self.connected = not isinstance(res, ErrorResult)
            if self.connected:
                # Remote sends a pickle_version in response to OP_START
                self.pickle_version = min(self.HIGHEST_PICKLE_PROTOCOL, res)
            callback(res)
        self.callbacks[0] = wrapped_callback

        self.reader.start()
        self.writer.write_raw(bubble)

        self.write_msg(
            OP_START,
            req_id=0,
            host=self.host,
            path=path,
            depthlimit=chopsticks.DEPTH_LIMIT,
        )

        self.errreader = ioloop.StderrReader(errloop, self.epipe, self.host)
        start_errloop()

    def on_error(self, err):
        err = ErrorResult(err)
        for id in list(self.callbacks):
            self.callbacks.pop(id)(err)

    def _join(self, timeout=5):
        end = time.time() + timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                return True
            time.sleep(0.01)
        return False

    def close(self):
        if not self.connected:
            return
        self.wpipe.close()  # Terminate child
        self.reader.stop()
        self.writer.stop()
        self._reset()

        if self._join(timeout=1):
            return

        # Send TERM
        self.proc.terminate()

        # Wait for process to shut down cleanly
        if self._join(timeout=5):
            return

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
        args = self.cmd_args()
        self.proc = subprocess.Popen(
            args,
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
    """A tunnel connected to a throwaway Docker container.

    :param name: The name of the Docker instance to create.
    :param image: The Docker image to launch. By default, download and run an
                  `official Docker Python image`__ corresponding to the
                  running Python version. `Official images are curated by
                  Docker`__.
    :param rm: If true, destroy the container when the tunnel is closed.

    .. __: https://hub.docker.com/_/python/
    .. __: https://docs.docker.com/docker-hub/official_repos/

    """
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
    """A tunnel that connects to a remote host over SSH.

    :param host: The hostname to connect to, as would be specified on an
                 ``ssh`` command line.
    :param user: The username to connect as.
    :param sudo: If true, use ``sudo`` on the remote end in order to run as
                 the ``root`` user. Use this when you can ``sudo`` to root but
                 not ``ssh`` directly as the root user.

    """
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

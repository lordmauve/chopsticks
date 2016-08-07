from __future__ import print_function
import subprocess
import sys
import os
import os.path
import pkgutil
import base64
import threading
import tempfile
from hashlib import sha1
from .ioloop import IOLoop, StderrReader

PY2 = sys.version_info < (3,)

if PY2:
    import cPickle as pickle
else:
    import pickle


__metaclass__ = type


# One global loop for all tunnels
loop = IOLoop()

# Another thread will output stderr
errloop = IOLoop()



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
        self.connect()

    def connect(self):
        """Connect the tunnel."""
        raise NotImplementedError('Subclasses must implement connect()')

    def write_msg(self, op, **kwargs):
        """Write one message to the subprocess.

        This uses a chunked JSON protocol.

        """
        kwargs['op'] = op
        self.writer.write(kwargs)

    def _next_id(self):
        self.req_id += 1
        return self.req_id

    def handle_imp(self, mod):
        if mod == '__main__':
            # Special-case main to find real main module
            main = sys.modules['__main__']
            path = main.__file__
            self.write_msg(
                'imp',
                mod=mod,
                exists=True,
                is_pkg=False,
                file=os.path.basename(path),
                source=open(path, 'r').read()
            )
            return

        stem = mod.replace('.', os.sep)
        paths = [
            (True, os.path.join(stem, '__init__.py')),
            (False, stem + '.py'),
        ]

        try:
            for root in sys.path:
                for is_pkg, rel in paths:
                    path = os.path.join(root, rel)
                    if os.path.exists(path):
                        self.write_msg(
                            'imp',
                            mod=mod,
                            exists=True,
                            is_pkg=is_pkg,
                            file=rel,
                            source=open(path, 'r').read()
                        )
                        return
        except:
            pass
        self.write_msg(
            'imp',
            mod=mod,
            exists=False,
            is_pkg=False,
            file=None,
            source=''
        )

    def on_message(self, msg):
        """Pump messages until the given ID is received.

        The current thread will be blocked until the response is received.

        """
        if 'tb' in msg:
            id = msg['req_id']
            error = ErrorResult(
                'Host %r raised exception; traceback follows' % self.host,
                msg['tb']
            )
            self.callbacks.pop(id)(error)
        elif 'imp' in msg:
            self.handle_imp(msg['imp'])
        elif 'ret' in msg:
            id = msg['req_id']
            if id not in self.callbacks:
                self._warn('response received for unknown req_id %d' % id)
                return

            self.callbacks.pop(id)(msg['ret'])
            self.reader.stop()
        elif 'data' in msg:
            id = msg['req_id']
            if id not in self.callbacks:
                self._warn('response received for unknown req_id %d' % id)
                return
            self.callbacks[id].recv(msg['data'])
        else:
            self._warn('malformed message received: %r' % msg)

    def _warn(self, msg):
        print('%s:' % self.host, msg, file=sys.stderr)

    def call(self, callable, *args, **kwargs):
        """Call the given callable on the remote host.

        The callable must return a value that can be serialised as JSON,
        but there is no such restriction on the parameters.

        """
        self._call_async(loop.stop, callable, *args, **kwargs)
        ret = loop.run()
        if isinstance(ret, ErrorResult):
            raise RemoteException(ret.msg)
        return ret

    def _call_async(self, on_result, callable, *args, **kwargs):
        id = self._next_id()
        self.callbacks[id] = on_result
        params = (callable, args, kwargs)
        self.reader.start()
        self.write_msg(
            'call',
            req_id=id,
            params=base64.b64encode(pickle.dumps(params, -1)).decode('ascii')
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
            'fetch',
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
            'begin_put',
            req_id=id,
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
                yield {
                    'op': 'end_put',
                    'req_id': req_id,
                    'sha1sum': chksum.hexdigest()
                }
                break
            chksum.update(chunk)
            data = base64.b64encode(chunk)
            if not PY2:
                data = data.decode('ascii')
            yield {
                'op': 'put_data',
                'req_id': req_id,
                'data': data
            }


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
        data = base64.b64decode(data)
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

        if isinstance(result, ErrorResult):
            os.unlink(self.local_path)
        self.on_result(result)


class PipeTunnel(BaseTunnel):
    """A tunnel that connects via a pair of unidirectional pipes.

    Subclasses will need to implement ``connect_pipes()`` to create the
    ``self.wpipe`` and ``self.rpipe`` pipe attibutes.

    """

    def connect(self):
        self.connect_pipes()
        self.wpipe.write(bubble)
        self.wpipe.flush()
        self.reader = loop.reader(self.rpipe, self.on_message, self.on_error)
        self.writer = loop.writer(self.wpipe)

        self.errreader = StderrReader(errloop, self.epipe, self.host)
        start_errloop()

    def on_error(self, err):
        err = ErrorResult(err)
        for id in list(self.callbacks):
            self.callbacks.pop(id)(err)


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

    def __del__(self):
        self.wpipe.close()  # Terminate child
        self.proc.wait()


class Local(SubprocessTunnel):
    """A tunnel to a subprocess on the same host."""
    def __init__(self, name='localhost'):
        self.host = name
        super(Local, self).__init__()


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
    def __init__(self, host, user=None):
        self.host = host
        self.user = user
        super(SubprocessTunnel, self).__init__()

    def cmd_args(self):
        args = ['ssh', '-o', 'PasswordAuthentication=no']
        if self.user:
            args.extend(['-l', self.user])
        args.append(self.host)
        args.extend(super(SSHTunnel, self).cmd_args())
        return ['"%s"' % w if ' ' in w else w for w in args]


# An alias, because this is the default tunnel type
Tunnel = SSHTunnel

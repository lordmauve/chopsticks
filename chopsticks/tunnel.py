from __future__ import print_function
import subprocess
import sys
import os
import os.path
import json
import struct
import pkgutil
import base64
import threading

PY2 = sys.version_info < (3,)

if PY2:
    import cPickle as pickle
else:
    import pickle

from .ioloop import IOLoop, StderrReader

__metaclass__ = type


# One global loop for all tunnels
loop = IOLoop()

# Another thread will output stderr
errloop = IOLoop()

bubble = pkgutil.get_data('chopsticks', 'bubble.py')


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
            self.msg += '\n\n' + tb

    def __repr__(self):
        return 'ErrorResult(%r)' % self.msg


    __str__ = __repr__
    __unicode__ = __repr__


class BaseTunnel:
    def __init__(self):
        self.req_id = 0
        self.callbacks = {}
        self.connect()

    def connect(self):
        """Connect the tunnel."""
        raise NotImplementedError('Subclasses must implement connect()')

    def write_msg(self, msg):
        """Write a JSON message to the tunnel."""
        raise NotImplementedError('Subclasses must implement write_msg()')

    def _next_id(self):
        self.req_id += 1
        return self.req_id

    def handle_imp(self, mod):
        stem = mod.replace('.', os.sep)
        paths = [
            (True, os.path.join(stem, '__init__.py')),
            (False, stem + '.py'),
        ]
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
            error = ErrorResult('RPC call failed', msg['tb'])
            self.callbacks.pop(id)(error)
        elif 'imp' in msg:
            self.handle_imp(msg['imp'])
        elif 'read' in msg:
            self.handle_read(msg['read'])
        elif 'ret' in msg:
            id = msg['req_id']
            if id not in self.callbacks:
                return

            self.callbacks.pop(id)(msg['ret'])
            self.reader.stop()

    def call(self, callable, *args, **kwargs):
        """Call the given callable on the remote host.

        The callable must return a value that can be serialised as JSON,
        but there is no such restriction on the parameters.

        """
        self._call_async(loop.stop, callable, *args, **kwargs)
        return loop.run()

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

    def write_msg(self, op, **kwargs):
        """Write one message to the subprocess.

        This uses a chunked JSON protocol.

        """
        kwargs['op'] = op
        self.writer.write(kwargs)


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
        args =[]
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

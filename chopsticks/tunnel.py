from __future__ import print_function
import subprocess
import sys
import os
import os.path
import json
import struct
import pkgutil
import base64
PY2 = sys.version_info < (3,)

if PY2:
    import cPickle as pickle
else:
    import pickle

from .ioloop import IOLoop

__metaclass__ = type


# One global loop for all tunnels
loop = IOLoop()


class BaseTunnel:
    bubble = None

    @classmethod
    def get_bubble(cls):
        if cls.bubble is None:
            cls.bubble = pkgutil.get_data('chopsticks', 'bubble.py')
        return cls.bubble

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
            raise IOError('Error from remote host:\n\n' + msg['tb'])
        if 'imp' in msg:
            self.handle_imp(msg['imp'])
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
        bubble = self.get_bubble()
        self.connect_pipes()
        self.wpipe.write(bubble)
        self.wpipe.flush()
        self.reader = loop.reader(self.rpipe, self.on_message, self.on_error)
        self.writer = loop.writer(self.wpipe)

    def on_error(self, err):
        print(str(err), file=sys.stderr)
        loop.stop()

    def write_msg(self, op, **kwargs):
        """Write one message to the subprocess.

        This uses a chunked JSON protocol.

        """
        kwargs['op'] = op
        self.writer.write(kwargs)


class SubprocessTunnel(PipeTunnel):
    """A tunnel that connects to a subprocess."""
    def connect_pipes(self):
        self.proc = subprocess.Popen(
            self.cmd_args(),
            bufsize=0,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            shell=False,
            preexec_fn=os.setpgrp
        )
        self.wpipe = self.proc.stdin
        self.rpipe = self.proc.stdout

    def cmd_args(self):
        bubble_bytes = len(self.get_bubble())
        python = '/usr/bin/python2' if PY2 else '/usr/bin/python3'
        return [
            '/usr/bin/env',
            '-i',
            python,
            '-usS',
            '-c',
            'import sys, os; sys.stdin = os.fdopen(0, \'rb\', 0); __bubble = sys.stdin.read(%d); exec(compile(__bubble, \'bubble.py\', \'exec\'))' % bubble_bytes
        ]

    def __del__(self):
        self.wpipe.close()  # Terminate child
        self.proc.wait()


class Local(SubprocessTunnel):
    """A tunnel to a subprocess on the same host."""
    def __init__(self, name='localhost'):
        self.host = name
        super(Local, self).__init__()


class SSHTunnel(SubprocessTunnel):
    """A tunnel that connects to a remote host over SSH."""
    def __init__(self, host, user=None):
        self.host = host
        self.user = user
        super(SubprocessTunnel, self).__init__()

    def cmd_args(self):
        args = ['ssh']
        if self.user:
            args.extend(['-l', self.user])
        args.append(self.host)
        args.extend(super(SSHTunnel, self).cmd_args())
        return ['"%s"' % w if ' ' in w else w for w in args]


# An alias, because this is the default tunnel type
Tunnel = SSHTunnel

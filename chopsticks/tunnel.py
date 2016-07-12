import subprocess
import sys
import os
import os.path
import cPickle as pickle
import json
import struct
import pkgutil
import base64

__metaclass__ = type


class BaseTunnel:
    bubble = None

    @classmethod
    def get_bubble(cls):
        if cls.bubble is None:
            cls.bubble = pkgutil.get_data('chopsticks', 'bubble.py')
        return cls.bubble

    def __init__(self):
        self.req_id = 0
        self.connect()

    def connect(self):
        """Connect the tunnel."""
        raise NotImplementedError('Subclasses must implement connect()')

    def write_msg(self, op, **kwargs):
        raise NotImplementedError('Subclasses must implement write_msg()')

    def read_msg(self):
        raise NotImplementedError('Subclasses must implement read_msg()')

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

    def _pump(self, for_id):
        """Pump messages until the given ID is received.

        The current thread will be blocked until the response is received.

        """
        while True:
            obj = self.read_msg()
            if 'tb' in obj:
                raise IOError('Error from remote host:\n\n' + obj['tb'])
            if 'imp' in obj:
                self.handle_imp(obj['imp'])
            elif 'ret' in obj and obj['req_id'] == for_id:
                return obj['ret']
            # TODO: dispatch requests for imports etc

    def call(self, callable, *args, **kwargs):
        """Call the given callable on the remote host.

        The callable must return a value that can be serialised as JSON,
        but there is no such restriction on the parameters.

        """
        id = self._next_id()
        params = (callable, args, kwargs)
        self.write_msg(
            'call',
            req_id=id,
            params=base64.b64encode(pickle.dumps(params))
        )
        return self._pump(id)

    def __del__(self):
        self.write_msg('end')
        self.proc.wait()


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

    def write_msg(self, op, **kwargs):
        """Write one message to the subprocess.

        This uses a chunked JSON protocol.

        """
        kwargs['op'] = op
        buf = json.dumps(kwargs)
        self.wpipe.write(struct.pack('!L', len(buf)))
        self.wpipe.write(buf)

    def read_msg(self):
        """Read one message from the subprocess.

        This decodes the stream using a chunked JSON protocol, which can be
        parsed without a security risk to the local host.

        """
        buf = self.rpipe.read(4)
        if not buf:
            raise IOError('Invalid message from remote.')
        (size,) = struct.unpack('!L', buf)
        return json.loads(self.rpipe.read(size))


class SubprocessTunnel(PipeTunnel):
    """A tunnel that connects to a subprocess."""
    def connect_pipes(self):
        self.proc = subprocess.Popen(
            self.cmd_args(),
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            shell=False
        )
        self.wpipe = self.proc.stdin
        self.rpipe = self.proc.stdout

    def cmd_args(self):
        bubble_bytes = len(self.get_bubble())
        return [
            '/usr/bin/env',
            '-i',
            '/usr/bin/python',
            '-usS',
            '-c',
            'import sys; __bubble = sys.stdin.read(%d); exec(compile(__bubble, \'bubble.py\', \'exec\'))' % bubble_bytes
        ]


class Local(SubprocessTunnel):
    """A tunnel to a subprocess on the same host."""
    def __init__(self):
        self.host = 'localhost'
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

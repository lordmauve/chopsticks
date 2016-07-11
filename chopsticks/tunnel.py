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


class Tunnel:
    bubble = None

    @classmethod
    def get_bubble(cls):
        if cls.bubble is None:
            cls.bubble = pkgutil.get_data('chopsticks', 'bubble.py')
        return cls.bubble

    def __init__(self, host, user=None):
        self.host = host
        self.user = user
        self.req_id = 0
        self.connect()

    def connect(self):
        bubble = self.get_bubble()
        self.proc = subprocess.Popen(
            self.ssh_cmd(),
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
        self.proc.stdin.write(bubble)
        self.proc.stdin.flush()

    def ssh_cmd(self):
        bubble_bytes = len(self.get_bubble())
        args =  ['ssh']
        if self.user:
            args.extend(['-l', self.user])
        args.extend([
            self.host,
            'PYTHONNOUSERSITE=1',
            '/usr/bin/python2',
            '-u',
            '-c',
            '"import sys; __bubble = sys.stdin.read(%d); exec compile(__bubble, \'bubble.py\', \'exec\')"' % bubble_bytes
        ])
        return args

    def _next_id(self):
        self.req_id += 1
        return self.req_id

    def write_msg(self, op, **kwargs):
        """Write one message to the subprocess.

        This uses a chunked JSON protocol.

        """
        kwargs['op'] = op
        buf = json.dumps(kwargs)
        self.proc.stdin.write(struct.pack('!L', len(buf)))
        self.proc.stdin.write(buf)

    def read_msg(self):
        """Read one message from the subprocess.

        This decodes the stream using a chunked JSON protocol, which can be
        parsed without a security risk to the local host.

        """
        buf = self.proc.stdout.read(4)
        if not buf:
            raise IOError('Invalid message from remote.')
        (size,) = struct.unpack('!L', buf)
        return json.loads(self.proc.stdout.read(size))

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

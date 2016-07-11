import subprocess
import sys
import os
import cPickle as pickle
import json
import struct
import pkgutil

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

    def write_msg(self, msg):
        """Write one message to the subprocess.

        Because we can already execute arbitrary code on the remote host,
        we can safely use pickle for the protocol in this direction, which
        is also the more important direction for our RPC.

        """
        pickle.dump(msg, self.proc.stdin)

    def read_msg(self):
        """Read one message from the subprocess.

        This decodes the stream using a chunked JSON protocol, which can be
        parsed without a security risk to the local host.

        """
        buf = self.proc.stdout.read(4)
        (size,) = struct.unpack('!L', buf)
        return json.loads(self.proc.stdout.read(size))

    def _pump(self, for_id):
        """Pump messages until the given ID is received.

        The current thread will be blocked until the response is received.

        """
        while True:
            obj = self.read_msg()
            if obj['req_id'] == for_id:
                return obj['ret']
            # TODO: dispatch requests for imports etc

    def call(self, callable, *args, **kwargs):
        """Call the given callable on the remote host.

        The callable must return a value that can be serialised as JSON,
        but there is no such restriction on the parameters.

        """
        id = self._next_id()
        msg = (id, callable, args, kwargs)
        self.write_msg(msg)
        return self._pump(id)

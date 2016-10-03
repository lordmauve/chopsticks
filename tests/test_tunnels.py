"""Test that we can execute code using tunnels."""
import time
import random
import sys
import os
import tempfile
import hashlib
from unittest import TestCase
from chopsticks.helpers import output_lines
from chopsticks.tunnel import Docker
from chopsticks.facts import python_version


def hash_pkg_data(pkg, fname):
    """Load package data and calculate the hash of it."""
    from hashlib import sha1
    import pkgutil
    return sha1(pkgutil.get_data(pkg, fname)).hexdigest()


class BasicTest(TestCase):
    def setUp(self):
        self.docker_name = 'unittest-%d' % random.randint(0, 1e9)
        self.tunnel = Docker(self.docker_name)

    def tearDown(self):
        del self.tunnel
        ls = output_lines(['docker', 'ps', '-a'])
        images = []
        for l in ls[1:]:
            ws = l.split()
            images.append(ws[-1])
        assert self.docker_name not in images, \
            "Image %r remained running after test" % self.docker_name

    def test_python_version(self):
        """We can call a function on a remote Docker."""
        ver = self.tunnel.call(python_version)
        self.assertEqual(tuple(ver[:2]), sys.version_info[:2])

    # The GPL is installed to a common path on the Docker
    # images we use
    GPL = '/usr/share/common-licenses/GPL'

    def test_fetch(self):
        """We can fetch a file from a remote Docker."""
        local = tempfile.mktemp()
        res = self.tunnel.fetch(
            remote_path=self.GPL,
            local_path=local
        )
        with open(local, 'rb') as f:
            data = f.read()
        self.assertEqual(res, {
            'local_path': local,
            'remote_path': '/usr/share/common-licenses/GPL',
            'sha1sum': hashlib.sha1(data).hexdigest(),
            'size': len(data)
        })

    def test_put(self):
        """We can copy a file to a remote Docker."""
        res = self.tunnel.put(
            local_path=self.GPL,
            remote_path='/tmp/gpl',
            mode=0o760
        )
        with open(self.GPL, 'rb') as f:
            data = f.read()
        self.assertEqual(res, {
            'remote_path': '/tmp/gpl',
            'sha1sum': hashlib.sha1(data).hexdigest(),
            'size': len(data)
        })
        out = self.tunnel.call(output_lines, ['ls', '-l', '/tmp'])
        for l in out[1:]:
            if 'gpl' in l:
                self.assertRegexpMatches(
                    l,
                    r'^-rwxrw---- 1 root root 35147 \w+ +\d+ \d+:\d+ gpl$'
                )
                return
        else:
            raise AssertionError('File not found in remote listing')

    def test_get_data(self):
        """We can load package data from the host."""
        hash = hash_pkg_data('chopsticks', 'bubble.py')
        remotehash = self.tunnel.call(
            hash_pkg_data, 'chopsticks', 'bubble.py'
        )
        self.assertEqual(
            remotehash,
            hash,
            msg='Failed to load bubble.py from host'
        )

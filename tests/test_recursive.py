"""Test that Chopsticks remote processes can launch tunnels."""
from unittest import TestCase
from chopsticks.helpers import output_lines
from chopsticks.tunnel import Local, Docker, RemoteException
from chopsticks.facts import python_version


def ping_docker():
    """Start a docker container and read out its Python version."""
    with Docker('unittest-36', image='python:3.6') as tun:
        return tun.call(python_version)[:2]


def recursive():
    """Infinite recursion, requiring depth limit to stop."""
    with Local() as tun:
        tun.call(recursive)


class RecursiveTest(TestCase):
    docker_name = 'unittest-36'

    def tearDown(self):
        ls = output_lines(['docker', 'ps', '-a'])
        images = []
        for l in ls[1:]:
            ws = l.split()
            images.append(ws[-1])
        assert self.docker_name not in images, \
            "Image %r remained running after test" % self.docker_name

    def test_python_version(self):
        """We can start a sub-tunnel from within a tunnel."""
        with Local() as tun:
            res = tun.call(ping_docker)
        self.assertEqual(
            res,
            [3, 6]
        )

    def test_depth_limit(self):
        """Recursive tunneling is limited by a depth limit."""
        with self.assertRaisesRegexp(
                RemoteException,
                r'.*DepthLimitExceeded: Depth limit of 2 ' +
                'exceeded at localhost -> localhost -> localhost'):
            recursive()


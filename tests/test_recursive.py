"""Test that Chopsticks remote processes can launch tunnels."""
from unittest import TestCase
from chopsticks.helpers import output_lines
from chopsticks.tunnel import Local, Docker
from chopsticks.facts import python_version


def ping_docker():
    """Start a docker container and read out its Python version."""
    with Docker('py36', image='python:3.6') as tun:
        return tun.call(python_version)[:2]


class RecursiveTest(TestCase):
    docker_name = 'py36'

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

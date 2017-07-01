"""Tests for miscellaneous properties, such as debuggability."""

from chopsticks.tunnel import Docker
from chopsticks.group import Group


def test_tunnel_repr():
    """Tunnels have a usable repr."""
    tun = Docker('py36', image='python:3.6')
    assert repr(tun) == "Docker('py36')"


def test_group_repr():
    """Groups have a usable repr."""
    grp = Group([
        Docker('py35', image='python:3.5'),
        Docker('py36', image='python:3.6')
    ])
    assert repr(grp) == "Group([Docker('py35'), Docker('py36')])"

"""Tests for miscellaneous properties, such as debuggability."""
import time
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


def test_group_reuse():
    """We can re-use a group."""
    grp = Group([
        Docker('py35', image='python:3.5'),
        Docker('py36', image='python:3.6')
    ])
    with grp:
        grp.call(time.time)
        grp.call(time.time)

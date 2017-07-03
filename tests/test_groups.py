"""Test that we can use groups."""
from chopsticks.group import Group
from chopsticks.tunnel import Docker
from chopsticks.facts import python_version


class PyDocker(Docker):
    """Docker tunnel for Python images."""
    # These Docker containers put their Python into /usr/local/bin/python,
    # regardless of 2/3. Because we just want to connect to whatever is in the
    # container here, we can override the 2/3 selection logic.
    python2 = python3 = 'python'


grp = Group([
    PyDocker('py27', image='python:2.7'),
    PyDocker('py35', image='python:3.5'),
    PyDocker('py36', image='python:3.6'),
])


def teardown_module():
    """Disconnect the group."""
    grp.close()


def is_py3():
    """Return True if the host is Python 3."""
    return tuple(python_version(short=True)) >= (3, 0)


def test_ping():
    """We can call a function on a group in parallel."""
    res = grp.call(python_version, short=True)
    assert dict(res) == {
        'py27': [2, 7],
        'py35': [3, 5],
        'py36': [3, 6]
    }


def test_filter_include():
    """We can filter hosts by a predicate function."""
    filtered = grp.filter(is_py3)
    hosts = sorted(t.host for t in filtered.tunnels)
    assert hosts == ['py35', 'py36']


def test_filter_exclude():
    """We can exclude hosts by a predicate function."""
    filtered = grp.filter(is_py3, exclude=True)
    hosts = sorted(t.host for t in filtered.tunnels)
    assert hosts == ['py27']

"""Test that we can use groups."""
import os.path
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
    PyDocker('unittest-27', image='python:2.7'),
    PyDocker('unittest-35', image='python:3.5'),
    PyDocker('unittest-36', image='python:3.6'),
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
        'unittest-27': [2, 7],
        'unittest-35': [3, 5],
        'unittest-36': [3, 6]
    }


def test_reuse_group():
    """We can re-use a group for multiple calls."""
    with grp:
        grp.call(python_version, short=True)
        grp.call(python_version, short=True)
        grp.call(python_version, short=True)


def test_fetch(tmpdir):
    """We can fetch files from multiple tunnels."""
    tmpdir = str(tmpdir)
    res = grp.fetch(
        remote_path='/etc/passwd',
        local_path=tmpdir + '/passwd-{host}'
    )
    res.raise_failures()
    assert sorted(v['local_path'] for v in res.values()) == [
        tmpdir + '/passwd-unittest-27',
        tmpdir + '/passwd-unittest-35',
        tmpdir + '/passwd-unittest-36',
    ]


def test_put():
    """We can put multiple files to multiple tunnels."""
    readme = os.path.join(os.path.dirname(__file__), '..', 'README.rst')
    size = os.stat(readme).st_size
    res = grp.put(
        local_path=readme,
        remote_path='/tmp/README.rst',
    )
    res.raise_failures()
    assert [v['size'] for v in res.values()] == [size] * 3


def test_filter_include():
    """We can filter hosts by a predicate function."""
    filtered = grp.filter(is_py3)
    hosts = sorted(t.host for t in filtered.tunnels)
    assert hosts == ['unittest-35', 'unittest-36']


def test_filter_exclude():
    """We can exclude hosts by a predicate function."""
    filtered = grp.filter(is_py3, exclude=True)
    hosts = sorted(t.host for t in filtered.tunnels)
    assert hosts == ['unittest-27']

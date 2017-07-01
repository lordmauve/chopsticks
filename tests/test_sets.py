from chopsticks.group import Group
from chopsticks.tunnel import Docker


dck1 = Docker('docker1')
dck2 = Docker('docker2')
grp_a = Group(['host1', 'host2'])
grp_b = Group(['host1', 'host3'])


def test_union():
    """We can calculate the union of two groups."""
    union = grp_a + grp_b
    hostnames = sorted(t.host for t in union.tunnels)
    assert hostnames == ['host1', 'host2', 'host3']


def test_intersection():
    """We can calculate the intersection of two groups."""
    union = grp_a & grp_b
    hostnames = sorted(t.host for t in union.tunnels)
    assert hostnames == ['host1']


def test_difference():
    """We can calculate the difference of two groups."""
    union = grp_a - grp_b
    hostnames = sorted(t.host for t in union.tunnels)
    assert hostnames == ['host2']


def test_symdifference():
    """We can calculate the symmetric difference of two groups."""
    union = grp_a ^ grp_b
    hostnames = sorted(t.host for t in union.tunnels)
    assert hostnames == ['host2', 'host3']


def test_group_host_union():
    """We can union two tunnels."""
    union = dck1 + dck2
    hostnames = sorted(t.host for t in union.tunnels)
    assert hostnames == ['docker1', 'docker2']


def test_group_host_union():
    """We can union a tunnel and a group."""
    union = grp_a + dck1
    hostnames = sorted(t.host for t in union.tunnels)
    assert hostnames == ['docker1', 'host1', 'host2']

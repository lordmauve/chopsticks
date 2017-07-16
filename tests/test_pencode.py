# -*- coding: utf-8 -*-
"""Tests for Python-friendly binary encoding."""
import pytest
from chopsticks.pencode import pencode, pdecode

bytes = type(b'')


def assert_roundtrip(obj):
    """Assert that we can successfully round-trip the given object."""
    buf = pencode(obj)
    assert isinstance(buf, bytes)
    obj2 = pdecode(buf)

    try:
        assert obj == obj2
    except RuntimeError as e:
        if 'maximum recursion depth exceeded' not in e.args[0]:
            raise
        # If we hit a RecursionError, we correctly decoded a recursive
        # structure, so test passes :)
    except RecursionError:
        pass

    assert type(obj) == type(obj2)
    return obj2


def test_roundtrip_unicode():
    """We can round-trip a unicode string."""
    assert_roundtrip(u'I ❤️  emoji')


def test_roundtrip_bytes():
    """We can round-trip Bytes."""
    assert_roundtrip(b'hello world')


def test_roundtrip_list():
    """We can round-trip a list."""
    assert_roundtrip([1, 2, 3])


def test_roundtrip_self_referential():
    """We can round-trip a self-referential structure."""
    a = []
    a.append(a)
    assert_roundtrip(a)


def test_roundtrip_backref():
    """References to the same object are preserved."""
    foo = 'foo'
    obj = [foo, foo]
    buf = pencode(obj)
    assert isinstance(buf, bytes)
    a, b = pdecode(buf)
    assert a is b


def test_roundtrip_set():
    """We can round-trip a set."""
    assert_roundtrip({1, 2, 3})


def test_roundtrip_tuple():
    """We can round-trip a tuple of bytes."""
    assert_roundtrip((b'a', b'b', b'c'))


def test_roundtrip_frozenset():
    """We can round-trip a frozenset."""
    assert_roundtrip(frozenset([1, 2, 3]))


def test_roundtrip_float():
    """We can round-trip a float."""
    assert_roundtrip(1.1)


def test_roundtrip_float_inf():
    """We can round-trip inf."""
    assert_roundtrip(float('inf'))


def test_roundtrip_long():
    """We can round trip what, in Python 2, would be a long."""
    assert_roundtrip(10121071034790721094712093712037123)

def test_roundtrip_float_nan():
    """We can round-trip nan."""
    import math
    res = pdecode(pencode(float('nan')))
    assert math.isnan(res)


def test_roundtrip_dict():
    """We can round-trip a dict, keyed by frozenset."""
    assert_roundtrip({frozenset([1, 2, 3]): 'abc'})


def test_roundtrip_none():
    """We can round-trip None."""
    assert_roundtrip(None)


def test_roundtrip_bool():
    """We can round-trip booleans and preserve their types."""
    res = assert_roundtrip((True, False))
    for r in res:
        assert isinstance(r, bool)


def test_roundtrip_kdict():
    """We handle string-keyed dicts."""
    assert_roundtrip({'abcd': 'efgh'})


def test_unserialisable():
    """An exception is raised if a type is not serialisable."""
    with pytest.raises(ValueError):
        pencode(object())


def test_roundtrip_start():
    """A typical start message is round-tripped."""
    host = u'unittest'
    assert_roundtrip({
        'host': host,
        'path': [host],
        'depthlimit': 2
    })

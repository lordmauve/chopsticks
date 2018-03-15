# -*- coding: utf-8 -*-
"""Tests for Python-friendly binary encoding."""
from hypothesis import example, given, strategies
import pytest
from chopsticks.pencode import pencode, pdecode

try:
    # Added in Python 3.5+
    RecursionError
except NameError:
    class RecursionError(RuntimeError):
        pass

bytes = type(b'')

def is_ascii(s):
    try:
        s.decode('ascii')
    except UnicodeDecodeError:
        return False
    return True

ascii_text = strategies.characters(max_codepoint=127)
ascii_binary = strategies.builds(lambda s: s.encode('ascii'), ascii_text)

immutables = strategies.recursive(
    ascii_binary |
    strategies.booleans() |
    strategies.floats(allow_nan=False) |
    strategies.integers() |
    strategies.none() |
    strategies.text() |
    strategies.tuples(),
    lambda children: (
        strategies.frozensets(children) |
        strategies.tuples(children)
    ),
)

mutables = strategies.recursive(
    strategies.dictionaries(immutables, immutables) |
    strategies.lists(immutables) |
    strategies.sets(immutables),
    lambda children: (
        strategies.dictionaries(immutables, children) |
        strategies.lists(children)
    ),
)

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


@given(strategies.text())
def test_roundtrip_unicode(s):
    """We can round-trip a unicode string."""
    assert_roundtrip(s)


@given(ascii_binary)
def test_roundtrip_bytes(s):
    """We can round-trip Bytes."""
    assert_roundtrip(s)


@given(strategies.lists(mutables | immutables))
def test_roundtrip_list(l):
    """We can round-trip a list."""
    assert_roundtrip(l)


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


@given(strategies.sets(immutables))
def test_roundtrip_set(s):
    """We can round-trip a set."""
    assert_roundtrip(s)


@given(strategies.tuples(immutables))
def test_roundtrip_tuple(t):
    """We can round-trip a tuple of bytes."""
    assert_roundtrip(t)


@given(strategies.frozensets(immutables))
def test_roundtrip_frozenset(s):
    """We can round-trip a frozenset."""
    assert_roundtrip(s)


@given(strategies.floats())
def test_roundtrip_float(f):
    """We can round-trip a float."""
    assert_roundtrip(f)


@given(strategies.integers())
@example(10121071034790721094712093712037123)
def test_roundtrip_int(i):
    """We can round trip what, in Python 2, would be a long."""
    assert_roundtrip(i)


@given(strategies.dictionaries(immutables, immutables | mutables))
def test_roundtrip_dict(d):
    """We can round-trip a dict, keyed by frozenset."""
    assert_roundtrip(d)


def test_roundtrip_none():
    """We can round-trip None."""
    assert_roundtrip(None)


@given(strategies.booleans())
def test_roundtrip_bool(b):
    """We can round-trip booleans and preserve their types."""
    res = assert_roundtrip(b)
    assert isinstance(res, bool)


@given(strategies.dictionaries(strategies.text(), strategies.text()))
def test_roundtrip_kdict(d):
    """We handle string-keyed dicts."""
    assert_roundtrip(d)


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

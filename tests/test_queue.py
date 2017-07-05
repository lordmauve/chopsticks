"""Test that we can use queues."""
import random
import time
from chopsticks.queue import Queue, AsyncResult
from chopsticks.tunnel import Docker, Local
from chopsticks.group import Group, GroupResult


def char_range(start, stop):
    start = ord(start)
    stop = ord(stop) + 1
    return ''.join(chr(c) for c in range(start, stop))


tunnel = None


def setup_module():
    global tunnel
    tunnel = Docker('unittest-%d' % random.randint(0, 1e9))


def teardown_module():
    global tunnel
    tunnel.close()
    tunnel = None


def test_result_set():
    """We can set a value on a result."""
    r = AsyncResult()
    r._set(123)
    assert r.value == 123


def test_result_callback():
    """We can set a value on a result."""
    result = []
    r = AsyncResult().with_callback(result.append)
    r._set(123)
    assert result == [123]


def test_queuing():
    """We can queue a couple of tasks and run them."""
    q = Queue()
    res1 = q.call(tunnel, char_range, b'a', b'c')
    res2 = q.call(tunnel, char_range, b'x', b'z')
    q.run()
    assert res1.value == 'abc'
    assert res2.value == 'xyz'


def test_queuing_parallel():
    """Queued tasks are run in parallel."""
    with Local() as loc:
        q = Queue()
        q.call(tunnel, time.sleep, 0.75)
        q.call(loc, time.sleep, 0.5)
        q.call(tunnel, time.sleep, 0.25)
        q.call(loc, time.sleep, 0.5)

        start = time.time()
        q.run()
        duration = time.time() - start

    # Assert that this was parallel because otherwise this couldn't have
    # completd in under 2 seconds.
    assert 1.0 < duration < 1.3


def test_enqueue_in_callback():
    """We can add new tasks from within a queue callback."""
    res = []
    tunnel2 = Local()
    def enqueue_next(result):
        res.append(q.call(tunnel2, char_range, b'x', b'z'))

    q = Queue()
    res.append(
        q.call(tunnel, char_range, b'a', b'c').with_callback(enqueue_next)
    )
    with Local():
        q.run()
    assert [r.value for r in res] == ['abc', 'xyz']


def test_enqueue_group():
    """We can use a Queue to call a Group method."""
    group = Group([
        Docker('unittest-%d' % random.randint(0, 1e9)),
        Docker('unittest-%d' % random.randint(0, 1e9))
    ])
    q = Queue()
    result = q.call(group, char_range, b'x', b'z')
    q.run()
    group.close()
    result.value.raise_failures()
    assert isinstance(result.value, GroupResult)
    assert [v for host, v in result.value.successful()] == ['xyz'] * 2


"""Test that we can use queues."""
import random
import time
try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock
from chopsticks.queue import Queue, AsyncResult
from chopsticks.tunnel import Docker, Local


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
    r.set(123)
    assert r.value == 123


def test_result_callback():
    """We can set a value on a result."""
    m = Mock()
    r = AsyncResult().with_callback(m)
    r.set(123)
    m.assert_called_once_with(123)


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

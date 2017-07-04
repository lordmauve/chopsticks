"""An API for feeding operations asynchronously to Chopsticks."""
from __future__ import print_function
import sys
import traceback
from types import MethodType
from functools import partial
from collections import defaultdict, deque
from .tunnel import loop, PY2, ErrorResult, RemoteException, BaseTunnel

__metaclass__ = type


class NotCompleted(Exception):
    """No value has been received by an AsyncResult."""


class AsyncResult:
    """The deferred result of a queued operation."""

    def __init__(self):
        self._callback = None
        self._value = NotCompleted

    def with_callback(self, callback):
        """Attach a callback to be called when a value is set."""
        # Chopsticks is not currently multithreaded, so in the intended usage
        # there is no race condition where a value could be set before the
        # callback is registered.
        #
        # We just validate that the usage is as intended.
        assert self._callback is None, "Callback already set."
        assert self._value is NotCompleted, "Value already set."
        self._callback = callback
        return self

    @property
    def value(self):
        """Get the value of the result.

        Raise NotCompleted if the task has not yet run.

        """
        if self._value is NotCompleted:
            raise NotCompleted('The operation has not completed.')
        return self._value

    def set(self, obj):
        """Set the value of the callback."""
        self._value = obj
        if self._callback:
            try:
                self._callback(self._value)
            except Exception:
                print('Error dispatching async callback', file=sys.stderr)
                traceback.print_exc()


def iteritems(d):
    """Compatibility shim for dict iteration."""
    if PY2:
        return d.iteritems()
    else:
        return d.items()


class Queue:
    """A queue of tasks to be performed.

    Queues build on Groups and Tunnels in order to feed tasks as quickly as
    possible to all connected hosts.

    """
    def __init__(self):
        self.queued = {}
        self.running = False

    def mkhandler(methname):
        """Create a wrapper for queueing the 'methname' operation."""
        def enqueue(self, target, *args, **kwargs):
            assert isinstance(target, BaseTunnel), \
                "Queue does not currently work with groups."""

            async_funcname = '_%s_async' % methname
            async_func = getattr(target, async_funcname)

            async_result = AsyncResult()
            try:
                queue = self.queued[target]
            except KeyError:
                queue = self.queued[target] = deque()
                self.connect(target)

            def callback(result):
                async_result.set(result)
                assert queue[0] is bound
                queue.popleft()
                if queue:
                    queue[0]()
                else:
                    del self.queued[target]
                    if not self.queued:
                        loop.stop()

            bound = partial(async_func, callback, *args, **kwargs)
            queue.append(bound)
            return async_result


        if PY2:
            enqueue.func_name == methname
        else:
            enqueue.__name__ = methname
        enqueue.__doc__ = (
            "Queue a %s operation to be run on the given target." % methname
        )
        return enqueue

    connect = mkhandler('connect')
    call = mkhandler('call')

    del mkhandler

    def run(self):
        self.running = True
        try:
            for host, queue in iteritems(self.queued):
                if not queue:
                    continue
                queue[0]()
            loop.run()
        finally:
            self.running = False

"""An API for feeding operations asynchronously to Chopsticks."""
from __future__ import print_function
import sys
import traceback
from types import MethodType
from functools import partial
from collections import defaultdict, deque
from .tunnel import loop, PY2, ErrorResult, RemoteException, BaseTunnel
from .group import Group, GroupOp

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

    def _set(self, obj):
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


    All methods accept a parameter `target`, which specifies which tunnels the
    operation should be performed with. This can be specified as a
    :class:`Tunnel` or a :class:`Group`.

    Each one returns an :class:`AsyncResult` which can be used to receive the
    result of the operation.

    """
    def __init__(self):
        self.queued = {}
        self.running = False

    def _enqueue_group(self, methname, group, args, kwargs):
        """Enqueue an operation on a Group of tunnels."""
        async_result = AsyncResult()
        op = GroupOp(async_result._set)
        for tunnel in group.tunnels:
            r = self._enqueue_tunnel(methname, tunnel, args, kwargs)
            r.with_callback(op.make_callback(tunnel.host))
        return async_result

    def _enqueue_tunnel(self, methname, tunnel, args, kwargs):
        """Enqueue an operation on a Tunnel."""
        async_funcname = '_%s_async' % methname
        async_func = getattr(tunnel, async_funcname)

        async_result = AsyncResult()
        try:
            queue = self.queued[tunnel]
        except KeyError:
            queue = self.queued[tunnel] = deque()
            self.connect(tunnel)
            if self.running:
                queue[0]()  # start the connect

        def callback(result):
            async_result._set(result)
            assert queue[0] is bound
            queue.popleft()
            if queue:
                queue[0]()
            else:
                del self.queued[tunnel]
                if not self.queued:
                    loop.stop()

        bound = partial(async_func, callback, *args, **kwargs)
        queue.append(bound)
        return async_result

    def mkhandler(methname):
        """Create a wrapper for queueing the 'methname' operation."""
        def enqueue(self, target, *args, **kwargs):
            if not isinstance(target, (BaseTunnel, Group)):
                raise TypeError(
                    'Invalid target; expected Tunnel or Group'
                )

            if isinstance(target, Group):
                m = self._enqueue_group
            else:
                m = self._enqueue_tunnel
            return m(methname, target, args, kwargs)

        if PY2:
            enqueue.func_name == methname
        else:
            enqueue.__name__ = methname
        enqueue.__doc__ = (
            "Queue a :meth:`~chopsticks.tunnel.BaseTunnel.{meth}()` operation "
            "to be run on the target.".format(meth=methname).lstrip()
        )
        return enqueue

    connect = mkhandler('connect')
    call = mkhandler('call')
    fetch = mkhandler('fetch')
    put = mkhandler('put')

    del mkhandler

    # fetch is slightly different because it constructs different local paths
    # for each host:

    def fetch(self, target, remote_path, local_path=None):
        """Queue a :meth:`~chopsticks.tunnel.BaseTunnel.fetch()` operation to be run on the target.  """  # noqa
        if isinstance(target, BaseTunnel):
            return self._enqueue_tunnel(
                'fetch', target,
                (),
                {'remote_path': remote_path, 'local_path': local_path}
            )

        async_result = AsyncResult()
        op = GroupOp(async_result._set)
        for tun, local_path in Group._local_paths(target.tunnels, local_path):
            r = self._enqueue_tunnel(
                'fetch', tun, (),
                {'remote_path': remote_path, 'local_path': local_path}
            )
            r.with_callback(op.make_callback(tun.host))
        return async_result

    def run(self):
        """Run all items in the queue.

        This method does not return until the queue is empty.

        """
        self.running = True
        try:
            for host, queue in iteritems(self.queued):
                if not queue:
                    continue
                queue[0]()
            loop.run()
        finally:
            self.running = False

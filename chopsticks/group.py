from .tunnel import SSHTunnel, loop, PY2, ErrorResult

__metaclass__ = type

if not PY2:
    basestring = str


class GroupResult(dict):
    """The results of a :meth:`Group.call()` operation.

    GroupResult behaves as a dictionary of results, keyed by hostname, although
    failures from individual hosts are represented as :class:`ErrorResult`
    objects.

    Methods are provided to easily process successes and failures separately.

    """
    if not PY2:
        def iteritems(self):
            """Implement iteritems() for Python 3."""
            return self.items()

    def successful(self):
        """Iterate over successful results as (host, value) pairs."""
        for host, res in self.iteritems():
            if isinstance(res, ErrorResult):
                continue
            yield host, res

    def failures(self):
        """Iterate over failed results as (host err) pairs."""
        for host, res in self.iteritems():
            if isinstance(res, ErrorResult):
                yield host, res

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            super(GroupResult, self).__repr__()
        )


class Group:
    """A group of hosts, for performing operations in parallel."""

    def __init__(self, hosts):
        """Construct a group from a list of tunnels or hosts.

        `hosts` may contain hostnames - in which case the connections will be
        made via SSH using the default settings. Alternatively, it may contain
        tunnel instances.

        """
        self.tunnels = []
        for h in hosts:
            if isinstance(h, basestring):
                h = SSHTunnel(h)
            self.tunnels.append(h)

    def _callback(self, host):
        def cb(ret):
            self.results[host] = ret
            self.waiting -= 1
            if self.waiting <= 0:
                results = self.results
                self.results = {}
                loop.stop(GroupResult(results))
        return cb

    def call(self, callable, *args, **kwargs):
        """Call the given callable on all hosts in the group.

        The given callable and parameters must be pickleable.

        However, the callable's return value has a tighter restriction: it must
        be serialisable as JSON, in order to ensure the orchestration host
        cannot be compromised through pickle attacks.

        The return value is a :class:`GroupResult`.

        """
        tunnels = self.tunnels[:]
        self.waiting = len(tunnels)
        self.results = {}
        for t in tunnels:
            t._call_async(self._callback(t.host), callable, *args, **kwargs)
        return loop.run()

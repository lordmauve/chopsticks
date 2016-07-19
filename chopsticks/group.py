from .tunnel import SSHTunnel, loop, PY2, ErrorResult

__metaclass__ = type

if not PY2:
    basestring = str


class GroupResult:
    def __init__(self, results):
        self.results = results

    def items(self):
        return self.results.items()

    def successful(self):
        """Iterate over successful results as (host, value) pairs."""
        for host, res in self.results.items():
            if isinstance(res, ErrorResult):
                continue
            yield host, res

    def failures(self):
        """Iterate over failed results as (host err) pairs."""
        for host, res in self.results.items():
            if isinstance(res, ErrorResult):
                yield host, res

    def __repr__(self):
        return '%s(%r)' % (
            self.__class__.__name__,
            self.results
        )


class Group:
    """A group of hosts, for performing operations in parallel."""
    def __init__(self, hosts):
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
        tunnels = self.tunnels[:]
        self.waiting = len(tunnels)
        self.results = {}
        for t in tunnels:
            t._call_async(self._callback(t.host), callable, *args, **kwargs)
        return loop.run()

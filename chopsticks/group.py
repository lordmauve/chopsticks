from .tunnel import SSHTunnel, loop, PY2

__metaclass__ = type

if not PY2:
    basestring = str


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
                loop.stop(results)
        return cb

    def call(self, callable, *args, **kwargs):
        tunnels = self.tunnels[:]
        self.waiting = len(tunnels)
        self.results = {}
        for t in tunnels:
            t._call_async(self._callback(t.host), callable, *args, **kwargs)
        return loop.run()

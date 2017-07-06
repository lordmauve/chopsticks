from .setops import SetOps
from .tunnel import SSHTunnel, loop, PY2, ErrorResult, pickle, RemoteException

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
        """Iterate over failed results as (host, err) pairs."""
        for host, res in self.iteritems():
            if isinstance(res, ErrorResult):
                yield host, res

    def raise_failures(self):
        """Raise a RemoteException if there were any failures."""
        failures = []
        for host, err in self.failures():
            failures.append(
                '[%s] %s' % (host, err.msg)
            )

        if failures:
            raise RemoteException(
                '{}/{} hosts had failures:\n\n{}'.format(
                    len(failures),
                    len(self),
                    '\n'.join(failures)
                )
            )

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            super(GroupResult, self).__repr__()
        )


class GroupOp:
    """An operation in progress on a group."""
    def __init__(self, callback):
        self.callback = callback
        self.results = {}
        self.waiting = 0

    def make_callback(self, host):
        """Return a callback to store a result for the given host.

        The callback will trigger the GroupOp's callback once all group
        results have been received.

        """
        def cb(ret):
            self.results[host] = ret
            self.waiting -= 1
            if self.waiting <= 0:
                self.callback(GroupResult(self.results))
        self.waiting += 1
        return cb


class Group(SetOps):
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
        self.connection_errors = {}

    def _new_op(self):
        self.op = GroupOp(loop.stop)
        self.op.results = self.connection_errors.copy()

    def _parallel(self, tunnels, method, *args, **kwargs):
        """Helper to call a method on all tunnels."""
        self._new_op()
        for t in tunnels:
            m = getattr(t, method)
            m(self.op.make_callback(t.host), *args, **kwargs)
        try:
            return loop.run()
        except:
            self.close()
            raise

    def connect(self):
        """Connect all tunnels."""
        self._connect(force=True)

    def _connect(self, force=False):
        """Connect all disconnected tunnels.

        Return a list of the tunnels we ended up connecting. Connection errors
        are saved into self.connection_errors.

        If force is False, don't attempt to reconnect tunnels that have
        failed to connect already.

        """
        all_tunnels = {}
        connected_tunnels = []
        disconnected_tunnels = []
        for t in self.tunnels:
            all_tunnels[t.host] = t
            if t.connected:
                connected_tunnels.append(t)
            else:
                if force or t.host not in self.connection_errors:
                    disconnected_tunnels.append(t)

        if not disconnected_tunnels:
            return connected_tunnels
        result = self._parallel(disconnected_tunnels, '_connect_async')

        self.connection_errors = {
            host: err
            for host, err in self.connection_errors.items()
            if host in all_tunnels
        }
        pickle_versions = [pickle.HIGHEST_PROTOCOL]
        for host, r in result.iteritems():
            t = all_tunnels[host]
            err = isinstance(r, ErrorResult)
            t.connected = not err
            if err:
                self.connection_errors[host] = r
            else:
                pickle_versions.append(r)

        # Use a common pickle version for all of these tunnels
        pickle_version = min(pickle_versions)
        for t in all_tunnels.values():
            t.pickle_version = pickle_version

        connected = set(all_tunnels) - set(self.connection_errors)
        return [t for t in all_tunnels.values() if t.host in connected]

    def close(self):
        """Close all tunnels."""
        for t in self.tunnels:
            t.close()

    def __enter__(self):
        """Connect all tunnels."""
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    def call(self, callable, *args, **kwargs):
        """Call the given callable on all hosts in the group.

        The given callable and parameters must be pickleable.

        However, the callable's return value has a tighter restriction: it must
        be serialisable as JSON, in order to ensure the orchestration host
        cannot be compromised through pickle attacks.

        The return value is a :class:`GroupResult`.

        """
        tunnels = self._connect()
        return self._parallel(tunnels, '_call_async', callable, *args, **kwargs)

    @staticmethod
    def _local_paths(tunnels, local_path):
        if local_path is not None:
            names = [local_path.format(host=t.host) for t in tunnels]
            if len(set(names)) != len(tunnels):
                raise ValueError(
                    'local_path template %s does not give unique paths' %
                    local_path
                )
            return zip(tunnels, names)
        else:
            return ((t, None) for t in tunnels)

    def fetch(self, remote_path, local_path=None):
        """Fetch files from all remote hosts.

        If `local_path` is given, it is a local path template, into which
        the tunnel's ``host`` name will be substituted using ``str.format()``.
        Hostnames generated in this way must be unique.

        For example::

            group.fetch('/etc/passwd', local_path='passwd-{host}')

        If `local_path` is not given, a temporary file will be used for
        each host.

        Return a :class:`GroupResult` of dicts, each containing:

        * ``local_path`` - the local path written to
        * ``remote_path`` - the absolute remote path
        * ``size`` - the number of bytes received
        * ``sha1sum`` - a sha1 checksum of the file data

        """
        tunnels = self._connect()

        self._new_op()
        for tun, local_path in self._local_paths(tunnels, local_path):
            tun._fetch_async(
                self.op.make_callback(tun.host),
                remote_path, local_path
            )
        try:
            return loop.run()
        except:
            self.close()
            raise

    def put(self, local_path, remote_path=None, mode=0o644):
        """Copy a file to all remote hosts.

        If remote_path is given, it is the remote path to write to. Otherwise,
        a temporary filename will be used (which will be different on each
        host).

        `mode` gives the permission bits of the files to create, or 0o644 if
        unspecified.

        This operation supports arbitarily large files (file data is streamed,
        not buffered in memory).

        Return a :class:`GroupResult` of dicts, each containing:

        * ``remote_path`` - the absolute remote path
        * ``size`` - the number of bytes received
        * ``sha1sum`` - a sha1 checksum of the file data

        """
        tunnels = self._connect()
        return self._parallel(
            tunnels, '_put_async',
            local_path, remote_path, mode
        )

    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.tunnels)

    def _as_group(self):
        return self

    def filter(self, predicate, exclude=False):
        """Return a Group of the tunnels for which `predicate` returns True.

        `predicate` must be a no-argument callable that can be pickled.

        If `exclude` is True, then return a Group that only contains tunnels
        for which predicate returns False.

        Raise RemoteException if any hosts could not be connected or fail to
        evaluate the predicate.

        """
        result = self.call(predicate)
        result.raise_failures()

        if exclude:
            op = lambda x: not x
        else:
            op = bool

        include = set(host for host, res in result.successful() if op(res))
        cls = type(self)
        return cls([t for t in self.tunnels if t.host in include])

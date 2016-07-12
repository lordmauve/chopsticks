Chopsticks
==========

Chopsticks is an orchestration library: it lets you manage and configure
remote hosts over SSH.

Naturally this is agentless and nothing needs to be installed on the remote
host.

It's perhaps best compared to Ansible or Fabric, but has some clever transport
magic which means it's very easy to develop with: you just write Python
functions that can be called from the orchestration host. No invoking bash
commands (eg. Fabric) or writing self-contained scripts with constrained input
and output formats (eg. Ansible).

Example
-------

With chopsticks you can simply import functions and hand them to the remote
host to be executed.

First stand up an SSH Tunnel::

    from chopsticks.tunnel import Tunnel
    tun = Tunnel('troy')

Then you can pass a function, to be called on the remote host::

    import time
    print('Time on %s:' % t.host, t.call(time.time))

The intention would be to build in some useful facts and config management
capabilities; currently only ``chopsticks.facts.ip`` is a thing::

    from chopsticks.facts import ip

    print('%s ip:' % t.host, t.call(ip))

API
---

Chopsticks should be used from a single thread; the following APIs are not
re-entrant.


``chopsticks.tunnel.Tunnel(host, user=None)``

    Construct an SSH Tunnel to connect to the given host. If ``user`` is given,
    connect as this user; otherwise connect as the default user (from SSH
    configs or the currently logged in user).

``chopsticks.tunnel.Local()``

    Construct a local tunnel, connected to a subprocess on the controller host.

    This could be used for testing.

``tunnel.call(callable, *args, **kwargs)``

    Call the given callable on the remote host with the given arguments.

    Any pickleable function can be called with any pickleable arguments.
    However, the function must return a value that is JSON-serializable. This
    constraint arises for security reasons, to ensure that any highjacking of
    the remote process cannot be used to compromise the controller machine.

``chopsticks.group.Group(hosts)``

    Construct a group of hosts; ``hosts`` may be a list of strings or a list
    of Tunnel objects.

``group.call(callable, *args, **kwargs)``

    Call the given callable on all hosts in the group.

    The return value is a dictionary of return values, keyed by host name (the
    host name passed to the ``Group``/``Tunnel`` constructor).

    The result key for a ``Local`` tunnel will be ``localhost``.


How it works
------------

The SSH tunnel invokes the ``python`` binary on the remote host, and feeds it a
bootstrap script via stdin.

Once bootstrapped, the remote "agent" sets up bi-directional communication over
the stdin/stdout of the tunnel (stderr is currently not consumed and can
therefore be used to feed debugging information back to the controlling
terminal). This communication is used (currently) for two purposes:

* An RPC system to invoke arbitrary callables within the remote agent and pass
  the returned values back to the controller.
* A PEP-302 import hook system, allowing the remote agent to import pure-Python
  code from the controller (NB. the controller can only serve Python modules
  that live within the filesystem - import hooks such as zipimport/compressed
  eggs are not currently supported).

stdin/stdout on the agent are redirected to ``/dev/null``.

License
-------

`Apache License 2.0`__

.. __: http://www.apache.org/licenses/LICENSE-2.0

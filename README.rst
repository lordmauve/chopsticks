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

One might also draw a comparison with Python's built-in ``multiprocessing``
library, but instead of calling code in subprocesses on the same host, the
code may be run on remote hosts.

Example
-------

With chopsticks you can simply import functions and hand them to the remote
host to be executed.

First stand up an SSH Tunnel::

    from chopsticks.tunnel import Tunnel
    tun = Tunnel('troy.example.com')

Then you can pass a function, to be called on the remote host::

    import time
    print('Time on %s:' % tun.host, tun.call(time.time))

The intention would be to build in some useful facts and config management
capabilities; currently only ``chopsticks.facts.ip`` is a thing::

    from chopsticks.facts import ip

    print('%s ip:' % tun.host, tun.call(ip))

``Tunnel`` provides support for executing on a single host; there is also a
``Group`` that can execute a callable on a number of hosts in parallel::

    from chopsticks.group import Group

    group = Group([
        'web1.example.com',
        'web2.example.com',
        'web3.example.com',
    ])
    for host, addr in group.call(ip).iteritems():
        print('%s ip:' % host, addr)

Installation
------------

Chopsticks can be used directly from a clone of the repo; or installed with
pip::

    $ pip install chopsticks


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


Python 2/3
----------

Chopsticks supports both Python 2 and Python 3.

Because Chopsticks takes the view that agents run out of the same codebase as
the controller, agents will attempt to use a similar Python interpreter to the
one for the controller process:

* ``/usr/bin/python2`` if the controller process is (any) Python 2.
* ``/usr/bin/python3`` if the controller process is (any) Python 3.


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

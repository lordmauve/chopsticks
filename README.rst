Chopsticks
==========

.. image:: https://badges.gitter.im/chopsticks-chat/Lobby.svg
   :alt: Join the chat at https://gitter.im/chopsticks-chat/Lobby
   :target: https://gitter.im/chopsticks-chat/Lobby?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge

Chopsticks is an orchestration library: it lets you manage and configure
remote hosts over SSH.

Naturally this is agentless and nothing needs to be installed on the remote
host except Python and an SSH agent.

It also has support for executing code in Docker containers.

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

First stand up an SSH Tunnel:

.. code:: python

    from chopsticks.tunnel import Tunnel
    tun = Tunnel('troy.example.com')

Then you can pass a function, to be called on the remote host:

.. code:: python

    import time
    print('Time on %s:' % tun.host, tun.call(time.time))

You can use any pure-Python function in the current codebase, meaning you can
create your own libraries of orchestration functions to call on remote hosts
(as well as functions that call out to remote hosts using Chopsticks).

``Tunnel`` provides support for executing on a single host; there is also a
``Group`` that can execute a callable on a number of hosts in parallel:

.. code:: python

    from chopsticks.group import Group

    group = Group([
        'web1.example.com',
        'web2.example.com',
        'web3.example.com',
    ])
    for host, addr in group.call(ip).successful():
        print('%s ip:' % host, addr)

Subclasses of tunnels allow connecting using streams other than SSH, such as
using ``sudo``, or to fresh Docker containers for sandboxing:

.. code:: python

    from chopsticks.tunnel import Docker
    from chopsticks.group import Group
    from chopsticks.facts import python_version

    group = Group([
        Docker('worker-1', image='python:3.4'),
        Docker('worker-2', image='python:3.5'),
        Docker('worker-3', image='python:3.6'),
    ])

    for host, python_version in group.call(python_version).items():
        print('%s Python version:' % host, python_version)

Tunnels and Groups connect lazily (or you can connect them proactively by
calling ``connect()``). They are also usable as context managers:

.. code:: python

    # Explictly connect and disconnect
    group.connect()
    group.call(time.time)
    group.close()

    # Reconnect and disconnect as context manager
    with group:
        group.call(time.time)

    # Implicit reconnect
    group.call(time.time)

    # Disconnect when destroyed
    del group

Naturally, any remote state (imports, globals, etc) is lost when the
Tunnel/Group is closed.

Installation
------------

Chopsticks can be used directly from a clone of the repo; or installed with
pip:

.. code:: bash

    $ pip install chopsticks


API
---

See `the full documentation`__ on Read The Docs.

.. __: https://chopsticks.readthedocs.io/


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
the stdin/stdout of the tunnel. This communication is used (currently) for two
purposes:

* An RPC system to invoke arbitrary callables within the remote agent and pass
  the returned values back to the controller.
* A PEP-302 import hook system, allowing the remote agent to import pure-Python
  code from the controller (NB. the controller can only serve Python modules
  that live within the filesystem - import hooks such as zipimport/compressed
  eggs are not currently supported).

``stderr`` is echoed to the controlling console, prefixed with a hostname to
identify which Tunnel it issued from. This can therefore be used to feed
debugging information back to the orchestration host.

License
-------

`Apache License 2.0`__

.. __: http://www.apache.org/licenses/LICENSE-2.0

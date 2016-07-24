Introduction
------------

With chopsticks you can simply import functions and hand them to the remote
host to be executed.

First stand up an SSH Tunnel::

    from chopsticks.tunnel import Tunnel
    tun = Tunnel('troy.example.com')

Then you can pass a function, to be called on the remote host::

    import time
    print('Time on %s:' % tun.host, tun.call(time.time))

You can use any pure-Python function in the current codebase, meaning you can
create your own libraries of orchestration functions to call on remote hosts
(as well as functions that call out to remote hosts using Chopsticks).
Naturally those functions can import pure-Python libraries and so on. Your
entire local codebase should just work remotely.

``Group`` allows for executing a callable on a number of hosts in parallel::

    from chopsticks.group import Group

    group = Group([
        'web1.example.com',
        'web2.example.com',
        'web3.example.com',
    ])
    for host, t in group.call(time.time).successful():
        print('Time on %s:' % host, t)

You can also run your code within Docker containers::

    from chopsticks.tunnel import Docker
    from chopsticks.facts import python_version

    dkr = Docker('py36', image='python:3.6')
    print(dkr.call(python_version))

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
the stdin/stdout of the tunnel. This communication is used (currently) for two purposes:

* An RPC system to invoke arbitrary callables within the remote agent and pass
  the returned values back to the controller.
* A PEP-302 import hook system, allowing the remote agent to import pure-Python
  code from the controller (NB. the controller can only serve Python modules
  that live within the filesystem - import hooks such as zipimport/compressed
  eggs are not currently supported).

stdin/stdout on the agent are redirected to ``/dev/null``, so calling
``print()`` on the remote machine will not break the tunnel.

``stderr`` is echoed to the controlling console, prefixed with a hostname to
identify which Tunnel it issued from. This can therefore be used to feed
debugging information back to the orchestration host.

Chopsticks vs ...
-----------------

It's natural to draw comparisons between Chopsticks and various existing tools,
but Chopsticks is a library, not an orchestration framework in its own right,
and other tools could potentially build on it.

Ansible
'''''''

Ansible's YAML syntax is a lot more restrictive than Python. It is friendly for
simple cases, but becomes increasingly ugly and convoluted as your scripts
become more complex. By writing your orchestration scripts in Python you can
take advantage of Python's rich ecosystem of syntax and tools for writing clean
Python code and documenting it, which apply even for very complicated use
cases.

Ansible's remote execution model involves dropping scripts, calling them, and
deleting them. In Ansible 2.1, some of Ansible's support code for Python-based
Ansible plugins gets shipped over SSH as part of a zipped bundle; but this
doesn't extend to your own code extentions. So Chopsticks is more easily and
naturally extensible: write your code how you like and let Chopsticks deal with
getting it running on the remote machine.

Fabric
''''''

The big difference between Fabric_ and Chopsticks is that Fabric will only
execute shell commands on the remote host, not Python callables. Of course you
can drop Python scripts and call them, but then you're back in Ansible
territory for extensibility, or you have to bootstrap the dependencies needed
to execute such scripts manually.

The difference in concept goes deeper: Fabric tries to be "of SSH", exploiting
all the cool SSH tunnelling features. Chopsticks doesn't care about SSH
specifically; it only cares about Python and pipes. This is what allows it to
work identically with Docker or subprocesses as with remote SSH hosts.

.. _Fabric: http://www.fabfile.org/

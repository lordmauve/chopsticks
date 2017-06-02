Tunnels
=======

Tunnels are the lowest-level API, used for invoking commands on an individual
host or container. For a higher-level API that allows invoking commands in
parallel across a range of hosts, see :doc:`groups`.

An established tunnel can be used to invoke commands and receive results.

Tunnel reference
----------------

.. currentmodule:: chopsticks.tunnel

SSH
'''

.. autoclass:: SSHTunnel
    :members: call, fetch, put

.. autoclass:: Tunnel


Docker
''''''

.. autoclass:: Docker


Subprocess
''''''''''


.. autoclass:: Local


Sudo
''''

.. autoclass:: Sudo

The :class:`Sudo` tunnel does not deal with password dialogues etc. In order
for this to work you must configure ``sudo`` not to need a password. You can
do this with these lines in ``/etc/sudoers``:

.. code-block:: none

    Cmnd_Alias PYTHON_CMDS = /usr/bin/python, /usr/bin/python2, /usr/bin/python3
    %somegroup   ALL=NOPASSWD: PYTHON_CMDS

This would allow users in the group ``somegroup`` to be able
to run the system Python interpreters using sudo, without
passwords.

.. warning::

    Naturally, as Chopsticks is a framework for executing arbitrary code, this
    allows executing arbitrary code as root. Only make this change if you are
    happy with relaxing security in this way.


Writing new tunnels
-------------------

It is possible to write a new tunnel driver for any system that allows you to
execute a ``python`` binary with direct relay of ``stdin`` and ``stdout``
pipes. To do this, simply subclass ``chopsticks.group.SubprocessTunnel``. Note
that all tunnel instances must have a ``host`` attibute which is used as the
key for the result in the :class:`GroupResult` dictionary when executing tasks
in a :class:`Group`.

So, strictly, these requirements apply:

* The tunnel setup machinery should not write to ``stdout`` - else you will
  have to identify and consume this output.
* The tunnel setup machinery should not read from ``stdin`` - else you will
  have to feed the required input.
* Both ``stdin`` and ``stdout`` must be binary-safe pipes.

The tunnel machinery may write to ``stderr``; this output will be presented to
the user.

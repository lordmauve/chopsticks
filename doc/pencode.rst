Result Serialisation
====================

The results of a :meth:`.Tunnel.call()` are serialised for passing to the
control host. Chopsticks provides its own serialisation format to achieve
security [1]_ while providing flexibility.

For simplicity, you can imagine this behaves like JSON, extended to support
most common Python types including ``tuple`` and ``set``.


Capabilities
------------

Generally Python primitive types are serialisable; classes are not. Currently
all of these Python types are serialisable:

* bytes/str/unicode (see :ref:`pencode-strings`)
* list
* tuple
* set
* frozenset
* dict
* bool
* int
* float
* None

The serialisation format also provides identity references, which can make
for more efficient encoding of certain types of structures. This also means
that self-referential (recursive) structures are supported.

.. _pencode-strings:

Unicode strings vs bytes
------------------------

As you may be aware, the distinction between "strings" and "bytes" was not
clear in Python 2.

If you're lucky enough to be using Python 3 on both the control host and remote
hosts, you can stop reading this section now. Python 3 has a strict separation
between bytes and strings and this just works.

If you're using Python 2 on both ends, you will also have few problems. You
can use byte strings (``str``), but they must contain only ASCII characters.
``unicode`` strings will work transparently.

For sending between Python 2 and Python 3, Chopsticks maps types in a way
designed to minimise functional problems. The upshot of this is that Python 2's
``str`` is treated as a ``str`` in Python 3. The problem presented by this is
that genuine 8-bit byte strings have no explicit type in Python 2.

Chopsticks provides a ``chopsticks.pencode.Bytes`` wrapper that allows 8-bit
binary data to be passed over the tunnel::

    from chopsticks.pencode import Bytes

    def my_method():
        return Bytes(b'\xa3100')


The full compatibility table is this:

+--------------+-------------------+-------------+-----------+
| Sending from | type              | to Py2      | to Py3    |
+==============+===================+=============+===========+
| Python 2     | ASCII ``str``     | ``str``     | ``str``   |
+--------------+-------------------+-------------+-----------+
| Python 2     | non-ASCII ``str`` | *forbidden*             |
+--------------+-------------------+-------------+-----------+
| Python 2     | ``unicode``       | ``unicode`` | ``str``   |
+--------------+-------------------+-------------+-----------+
| Python 2     | ``pencode.Bytes`` | ``str``     | ``bytes`` |
+--------------+-------------------+-------------+-----------+
| Python 3     | ``str``           | ``unicode`` | ``str``   |
+--------------+-------------------+-------------+-----------+
| Python 3     | ``bytes``         | ``str``     | ``bytes`` |
+--------------+-------------------+-------------+-----------+
| Python 3     | ``pencode.Bytes`` | ``str``     | ``bytes`` |
+--------------+-------------------+-------------+-----------+

.. [1] Pickle is not suitable, because this could allow malicious software
       installed on remote hosts to compromise the control machine by executing
       arbitrary code. Executing arbitrary code in the other direction, of
       course, is the point of Chopsticks.

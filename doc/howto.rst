How to...
=========

How to write a single-file Chopsticks script
--------------------------------------------

It is possible to write a single-file Chopsticks script, but note that
Chopsticks itself is not currently importable on the remote agent (due to
`issue #6`_), so ensure that the import of Chopsticks is wrapped in an
``if __name__ == '__main__':`` block::

    def do_it():
        return 'done'

    if __name__ == '__main__':  # Then we're on the controller side
        from chopsticks import Tunnel
        tunnel = Tunnel('remote')
        tunnel.call(do_it)

.. _`issue #6`: https://github.com/lordmauve/chopsticks/issues/6

How to customise interpreter paths
----------------------------------

Chopsticks assumes that the interpreter path on a remote host will be
``/usr/share/python2`` for Python 2 and ``/usr/share/python3`` for Python 3.
However, these paths may not always be correct.

To override the path of the interpreter you can simple subclass :class:`Tunnel`
(or the tunnel type you wish to use), and modify the ``python2`` and
``python3`` class attributes::

    class MyTunnel(Tunnel):
        python3 = '/usr/local/bin/python2'

To do this for all tunnels of the same type, modify the attribute on the type::

    Tunnel.python2 = '/usr/bin/python2'

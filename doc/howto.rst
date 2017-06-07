How to...
=========

How to write a single-file Chopsticks script
--------------------------------------------

Chopsticks will work very well with a neatly organised codebase of management
functions, but you can also write a single file script.

Chopsticks has special logic to handle this case, which is different from
the standard import machinery.

The cleanest way to write this script would be::

    from chopsticks import Tunnel


    def do_it():
        return 'done'


    if __name__ == '__main__':
        with Tunnel('remote') as tun:
            tun.call(do_it)


Actually, only the ``do_it()`` function, and various globals it uses, are sent
to the remote host. This code will work just fine::


    from chopsticks import Tunnel


    def do_it():
        return 'done'


    tunnel = Tunnel('remote')
    tunnel.call(do_it)


This also allows Chopsticks to be used from within `Jupyter Notebooks`_.

.. _`Jupyter Notebooks`: http://jupyter.org/


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

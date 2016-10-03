How to...
=========

How to write a single-file Chopsticks script
--------------------------------------------

Chopsticks will work very well with a neatly organised codebase of management
functions, but for a quick and easily distributed script, it is possible to
write a single-file Chopsticks script. Several caveats apply, however.

First, you very certainly don't want to recursively open sub-tunnels, so
only start a tunnel if you're executing `__main__`::

    def do_it():
        return 'done'

    if __name__ == '__main__':  # This line is important
        from chopsticks import Tunnel
        tunnel = Tunnel('remote')
        tunnel.call(do_it)


Note that importing ``chopsticks`` adds a few round trips, and this isn't
needed on the remote side, which is why we only do that import within the
``if __name__ == '__main__':`` block.

Python 2 doesn't support monkey-patching of the ``__main__`` module in the
same way as Python 3, and therefore requires an extra trick.
Say your script is called ``my_script.py``. Then you should re-import your
functions from the ``my_script`` module, which will make them importable on
the remote host::

    def my_remote_func():
        ...

    if __name__ == '__main__':
        from my_script import my_remote_func
        # now my_remote_func is my_script.my_remote_func, which can
        # be unpickled
        from chopsticks.tunnel import Tunnel
        Tunnel(hostname).call(my_remote_func)

See `issue #7`__ to track the status of this issue.

.. __: https://github.com/lordmauve/chopsticks/issues/7

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

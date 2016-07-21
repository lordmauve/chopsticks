Groups
======

Groups can be used to perform a remote operation in parallel across a number
of hosts, and collect the results.


Group API
'''''''''

.. currentmodule:: chopsticks.group

.. autoclass:: Group
    :members: __init__, call


Results
'''''''

.. autoclass:: GroupResult
    :members: failures, successful

.. autoclass:: ErrorResult

    Error results provide the following attributes:

    .. attribute:: msg

        A human-readable error message.

    .. attribute:: tb

        The traceback from the remote host as a string, or ``None`` if
        unavailable.


Examples
''''''''

For example, this code::


    from chopsticks.facts import ip
    from chopsticks.group import Group

    group = Group([
        'web1.example.com',
        'web2.example.com',
        'web3.example.com',
    ])
    for host, addr in group.call(ip).items():
        print('%s ip:' % host, addr)

might output::

    web1.example.com ip: 196.168.10.5
    web3.example.com ip: 196.168.10.7
    web2.example.com ip: 196.168.10.6

You could also construct a group from existing tunnels - or mix and match::

    all_hosts = Group([
        'web1.example.com',
        Docker('example'),
        Local('worker')
    ])

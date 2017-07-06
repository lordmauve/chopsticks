Version History
===============


1.0 - 2017-07-06
----------------

API Changes
'''''''''''

* New :class:`.Queue` API for asynchronous operations and scheduling different
  tasks onto different hosts.
* Chopsticks can be imported and used on remote hosts (see :ref:`recursive`).
* Functions defined in ``__main__`` modules or Jupyter notebooks can now be
  sent to remote hosts.
* Tunnels and Groups now connect lazily.
* Tunnels and Groups can be used as context managers to ensure they are closed.
* Tunnels and Groups can be reconnected once closed.
* Tunnels and Groups now support :ref:`set operations <setops>` (union,
  difference, etc).  Tunnels behave as a group of one tunnel.
* New :meth:`.Group.filter()` method allows filtering hosts by executing a
  function on each host.
* Added a :class:`.Sudo` tunnel, to run as a different user on the local
  machine.
* Added a ``sudo`` parameter to :class:`.SSHTunnel`, to run as ``root`` on a
  remote host.
* New :meth:`.GroupResult.raise_failures()` allows converting ``ErrorResult``
  to exceptions.


Internal Changes
''''''''''''''''

* Parameters are now sent over the tunnels using a custom binary protocol,
  rather than JSON. This is more efficient for byte strings, as used in the
  importer machinery.
* Automatically configure the highest pickle version to use based on what is
  supported by the host.


0.5 - 2016-08-07
----------------

* :meth:`.Group.put()` and :meth:`.Group.fetch()` methods allow sending and
  receiving files from Tunnels in parallel.
* Raise exceptions when Tunnel methods fail.


0.4 - 2016-07-24
----------------

* Prefix lines of stderr from tunnels with hostname.
* New :class:`.Docker` tunnel, to open a tunnel into a new container.
* Added Sphinx documentation, on readthedocs.org.


0.3 - 2016-07-15
----------------

* Added support for Python 3.


0.2 - 2016-07-13
----------------

* Add :class:`.Group` for running operations on multiple hosts in parallel.


0.1 - 2016-07-12
----------------

* Initial public version

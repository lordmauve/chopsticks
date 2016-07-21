.. Chopsticks documentation master file, created by
   sphinx-quickstart on Thu Jul 21 07:59:54 2016.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Chopsticks - a Pythonic orchestration library
=============================================

Chopsticks is an orchestration library: it lets you manage and configure
remote hosts over SSH.

Naturally this is agentless and nothing needs to be installed on the remote
host except Python and an SSH agent.

Chopsticks was built for extensibility. Remote hosts may import Python code
from the orchestration host on demand, so remote agents can immediately use
new functions you define. In effect, you have access to the same codebase on
remote hosts as on the orchestration host.

Contents:

.. toctree::
    :maxdepth: 2

    intro
    tunnels
    groups


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


"""Exercise chopsticks serial APIs."""
from __future__ import print_function
from chopsticks.tunnel import Tunnel, Local
from chopsticks.facts import ip, python_version
import time

hosts = [
    Tunnel('byzantium'),
#    Tunnel('office'),
    Local()
]
for t in hosts:
    print('Time on %s:' % t.host, t.call(time.time))
    print('%s ip:' % t.host, t.call(ip))
    print('%s Python version: %s' % (t.host, t.call(python_version)))
    print()

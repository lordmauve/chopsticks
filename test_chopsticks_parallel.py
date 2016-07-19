"""Exercise the chopsticks parallel API."""
from __future__ import print_function
from chopsticks.tunnel import Local, Docker
from chopsticks.group import Group
import chopsticks.facts
import time

group = Group([
    Local('worker-1'),
    'byzantium',
    'office',
    Docker('docker-1')
])
for host, t in group.call(time.time).successful():
    print('Time on %s:' % host, t)

print()

for host, addr in group.call(chopsticks.facts.ip).successful():
    print('%s ip:' % host, addr)

print()

for host, ver in group.call(chopsticks.facts.python_version).successful():
    print('%s Python version:' % host, tuple(ver))

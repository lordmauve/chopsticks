"""Exercise the chopsticks parallel API."""
from __future__ import print_function
from chopsticks.tunnel import Local
from chopsticks.group import Group
from chopsticks.facts import ip, python_version
import time

group = Group([
    Local('worker-1'),
    Local('worker-2'),
    'byzantium'
])
for host, t in group.call(time.time).items():
    print('Time on %s:' % host, t)

print()

for host, addr in group.call(ip).items():
    print('%s ip:' % host, addr)

print()

for host, ver in group.call(python_version).items():
    print('%s Python version:' % host, tuple(ver))

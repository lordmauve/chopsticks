"""Exercise the chopsticks parallel API."""
from __future__ import print_function
from chopsticks.tunnel import Local
from chopsticks.group import Group
from chopsticks.facts import ip
import time

group = Group([
    'byzantium',
    'office',
    Local()
])
for host, t in group.call(time.time).iteritems():
    print('Time on %s:' % host, t)

print()

for host, addr in group.call(ip).iteritems():
    print('%s ip:' % host, addr)


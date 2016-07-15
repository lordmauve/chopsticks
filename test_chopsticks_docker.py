"""Exercise the chopsticks Docker connectivity."""
from __future__ import print_function
from chopsticks.tunnel import Docker
from chopsticks.group import Group
from chopsticks.facts import python_version

group = Group([
    Docker('worker-1', image='python:3.4'),
    Docker('worker-2', image='python:3.5'),
    Docker('worker-3', image='python:3.6'),
])

for host, python_version in group.call(python_version).items():
    print('%s Python version:' % host, python_version)

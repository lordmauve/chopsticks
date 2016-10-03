"""Exercise the chopsticks Docker connectivity."""
import sys
from chopsticks.facts import python_version
from funcs import print_is_function

def hello():
    print >>sys.stderr, "hello"
    return "hello chopsticks"


if __name__ == '__main__':
    from chopsticks.tunnel import Docker
    from chopsticks.group import Group
    group = Group([
        Docker('worker-1'),
#       Docker('worker-1', image='python:3.4'),
#        Docker('worker-2', image='python:3.5'),
#        Docker('worker-3', image='python:3.6'),
    ])

    for host, result in group.call(print_is_function).items():
        print(host, result)
#    for host, python_version in group.call(python_version).items():
#        print('%s Python version:' % host, python_version)

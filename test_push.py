from __future__ import print_function
from chopsticks.tunnel import Tunnel, Docker, Local
from chopsticks.group import Group
from chopsticks.helpers import check_output
from chopsticks.facts import python_version

t = Docker('test-1')
res = t.put('/usr/share/common-licenses/GPL', 'blah', mode=0o755)
print(res)

print(t.call(python_version))

print(t.call(check_output, ['ls', '-l', res['remote_path']]))

g = Group([t, Docker('test-2')])
for host, res in g.put('/usr/share/common-licenses/GPL').successful():
    print(host, res)

for host, res in g.call(check_output, ['ls', '-l', '/tmp']).successful():
    print(host)
    print(res)

from __future__ import print_function
from chopsticks.tunnel import Tunnel, Docker
from chopsticks.group import Group

t = Tunnel('byzantium')
res = t.fetch('/etc/passwd', 'byzantium-passwd')
print(res)
print(open(res['local_path']).read())

del t

g = Group(['byzantium', 'office', Docker('docker-1')])
for host, res in g.fetch('/etc/passwd', local_path='fetches/passwd-{host}').successful():
    print(host, res)
    print(open(res['local_path']).read())

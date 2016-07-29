from __future__ import print_function
from chopsticks.tunnel import Tunnel

t = Tunnel('byzantium')
res = t.fetch('/etc/passwd')
print(res)
print(open(res['local_path']).read())

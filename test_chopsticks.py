from __future__ import print_function
from chopsticks.tunnel import Tunnel
from chopsticks.facts import ip
import time

t = Tunnel('byzantium')
print('Time on byzantium:', t.call(time.time))
print('byzantium ip:', t.call(ip))

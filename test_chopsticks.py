from __future__ import print_function
from chopsticks import Tunnel
import time

t = Tunnel('byzantium')
print('Time on byzantium:', t.call(time.time))

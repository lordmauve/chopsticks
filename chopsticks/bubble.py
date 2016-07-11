import sys
sys.path = [p for p in sys.path if p.startswith('/usr')]

def debug(msg):
    print >>sys.stderr, msg

# Reshuffle fds so that we can't break our transport by printing to stdout
import os
infd = os.dup(0)
outfd = os.dup(1)
inpipe = os.fdopen(infd, 'rb')
outpipe = os.fdopen(outfd, 'wb', 0)
sys.stdin.close()
sys.stdin = open(os.devnull, 'rb')
sys.stdout.close()
sys.stdout = open(os.devnull, 'wb')

import threading
from Queue import Queue
import cPickle as pickle
import json
import struct

outqueue = Queue()
done = object()

running = True

def reader():
    while True:
        try:
            obj = pickle.load(inpipe)
        except:
            obj = None
        if obj is None:
            outqueue.put(done)
            break
        req_id, callable, args, kwargs = obj
        try:
            ret = callable(*args, **kwargs)
        except:
            import traceback
            msg = {
                'req_id': req_id,
                'tb': traceback.format_exc()
            }
        else:
            msg = {
                'req_id': req_id,
                'ret': ret,
            }
        outqueue.put(msg)


def writer():
    while True:
        msg = outqueue.get()
        if msg is done:
            break
        # pickle is unsafe for the return transport
        buf = json.dumps(msg)
        outpipe.write(struct.pack('!L', len(buf)))
        outpipe.write(buf)


for func in (reader, writer):
    threading.Thread(target=func).start()

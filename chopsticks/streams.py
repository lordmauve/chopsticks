"""Support for streaming files over a tunnel."""
import weakref

id = 0
files = weakref.WeakValueDictionary()


class File:
    def __new__(cls, *args, **kwargs):
        global id
        inst = type.__new__(cls, *args, **kwargs)
        id += 1
        inst.id = id
        files[id] = inst
        return inst


class SendFile(File):
    """A SendFile is used for sending file data through a tunnel.

    This allows for arbitrary-sized data to be sent to hosts. Files that fit
    in memory need not use this.

    """
    def __init__(self, path):
        self.path = path

    def __reduce__(self):
        return (ReadFile, (self.id,))



class ReadFile(object):
    def __init__(self, id):
        self.id = id

    def write_to(self, path):
        """Initiate the transfer, writing the data to the given path."""
        pass

    def __reduce__(self):
        raise TypeError('%r is not pickleable' % self)




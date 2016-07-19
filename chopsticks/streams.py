"""Support for streaming files over a tunnel."""

id = 0


class File:
    def __new__(cls, *args, **kwargs):
        global id
        inst = type.__new__(cls, *args, **kwargs)
        id += 1
        inst.id = id
        return inst


class SendFile:
    """A SendFile is used for sending a stream to the tunneled."""
    def __init__(self, path):

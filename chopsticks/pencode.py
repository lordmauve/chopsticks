"""Tiny binary JSON struct encoder.

We use this in preference to JSON primarily because it can handle the
difference between bytes and unicode strings, which is much more efficient
than encoding bytes-as-base64-in-JSON.

"""
import struct
import codecs

SZ = struct.Struct('!I')

utf8_decode = codecs.getdecoder('utf8')


PY3 = bool(1 / 2)
PY2 = not PY3

if PY3:
    unicode = str
else:
    bytes = str


def bsz(seq):
    """Encode the length of a sequence as a big-endian 4-byte unsigned int."""
    return SZ.pack(len(seq))


def pencode(obj):
    """Encode the given Python primitive structure, returning a byte string."""
    out = []
    _pencode(obj, out)
    return b''.join(out)


def _pencode(obj, out):
    """Inner function for encoding of structures."""
    if isinstance(obj, bytes):
        out.extend([b'b', bsz(obj), obj])
    elif isinstance(obj, unicode):
        bs = obj.encode('utf8')
        out.extend([b's', bsz(bs), bs])
    elif isinstance(obj, bool):
        out.extend([b'1', b't' if obj else b'f'])
    elif isinstance(obj, int):
        bs = str(int(obj)).encode('ascii')
        out.extend([b'i', bsz(bs), bs])
    elif isinstance(obj, (tuple, list)):
        code = b'l' if isinstance(obj, list) else b't'
        out.extend([code, bsz(obj)])
        for item in obj:
            _pencode(item, out)
    elif isinstance(obj, dict):
        out.extend([b'd', bsz(obj)])
        for k in obj:
            if isinstance(k, str):
                if PY2:
                    kbs = str(k)
                else:
                    kbs = str(k).encode('utf8')
                out.extend([b'k', bsz(kbs), kbs])
            else:
                _pencode(k, out)
            _pencode(obj[k], out)
    elif obj is None:
        out.append(b'n')
    else:
        raise ValueError('Unserialisable type %s' % type(obj))


class obuf(object):
    """Wrapper to unpack data from a buffer."""
    def __init__(self, buf):
        self.buf = buf
        self.offset = 0

    def read_size(self):
        v = SZ.unpack_from(self.buf, self.offset)[0]
        self.offset += SZ.size
        return v

    def read_bytes(self, n):
        start = self.offset
        end = self.offset = start + n
        return self.buf[start:end]


def pdecode(buf):
    """Decode a pencoded byte string to a structure."""
    return _decode(obuf(buf))


def _decode(obuf):
    code = obuf.read_bytes(1)
    if code == b'k':
        code = b'b' if PY2 else b's'

    if code == b'n':
        return None
    elif code == b'b':
        sz = obuf.read_size()
        return obuf.read_bytes(sz)
    elif code == b's':
        sz = obuf.read_size()
        return utf8_decode(obuf.read_bytes(sz))[0]
    elif code == b'1':
        return obuf.read_bytes(1) == b't'
    elif code == b'i':
        sz = obuf.read_size()
        return int(obuf.read_bytes(sz))
    elif code == b'l':
        sz = obuf.read_size()
        return [_decode(obuf) for _ in range(sz)]
    elif code == b't':
        sz = obuf.read_size()
        return tuple(_decode(obuf) for _ in range(sz))
    elif code == b'd':
        sz = obuf.read_size()
        return dict((_decode(obuf), _decode(obuf)) for _ in range(sz))
    else:
        raise ValueError('Unknown pack opcode %r' % code)

"""Tiny binary JSON struct encoder.

We use this in preference to JSON primarily because it can handle the
difference between bytes and unicode strings, which is much more efficient
than encoding bytes-as-base64-in-JSON.

"""
import sys
import struct
import codecs

SZ = struct.Struct('!I')

utf8_decode = codecs.getdecoder('utf8')


PY3 = sys.version_info >= (3,)
PY2 = not PY3

if PY3:
    unicode = str
    range_ = range
    long = int
else:
    bytes = str
    range_ = xrange


def pencode(obj):
    """Encode the given Python primitive structure, returning a byte string."""
    p = Pencoder()
    p._pencode(obj)
    return p.getvalue()


def bsz(seq):
    """Encode the length of a sequence as big-endian 4-byte uint."""
    return SZ.pack(len(seq))


SEQTYPE_CODES = {
    set: b'q',
    frozenset: b'Q',
    list: b'l',
    tuple: b't',
}
CODE_SEQTYPES = dict((v, k) for k, v in SEQTYPE_CODES.items())


class Pencoder(object):
    def __init__(self):
        self.out = []
        self.objs = 0
        self.backrefs = {}

    def getvalue(self):
        return b''.join(self.out)

    def _pencode(self, obj):
        """Inner function for encoding of structures."""
        out = self.out
        objid = id(obj)
        if objid in self.backrefs:
            out.extend([b'R', SZ.pack(self.backrefs[objid])])
            return
        else:
            self.backrefs[objid] = len(self.backrefs)

        otype = type(obj)

        if isinstance(obj, bytes):
            out.extend([b'b', bsz(obj), obj])
        elif isinstance(obj, unicode):
            bs = obj.encode('utf8')
            out.extend([b's', bsz(bs), bs])
        elif isinstance(obj, bool):
            out.extend([b'1', b't' if obj else b'f'])
        elif isinstance(obj, (int, long)):
            bs = str(int(obj)).encode('ascii')
            out.extend([b'i', bsz(bs), bs])
        elif isinstance(obj, float):
            bs = str(float(obj)).encode('ascii')
            out.extend([b'f', bsz(bs), bs])
        elif otype in SEQTYPE_CODES:
            code = SEQTYPE_CODES[otype]
            out.extend([code, bsz(obj)])
            for item in obj:
                self._pencode(item)
        elif isinstance(obj, dict):
            out.extend([b'd', bsz(obj)])
            for k in obj:
                self._pencode(k)
                self._pencode(obj[k])
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
    return PDecoder().decode(buf)


class PDecoder(object):
    def __init__(self):
        self.br_count = 0
        self.backrefs = {}

    def decode(self, buf):
        return self._decode(obuf(buf))

    def _decode(self, obuf):
        br_id = self.br_count
        self.br_count += 1

        code = obuf.read_bytes(1)
        if code == b'n':
            obj = None
        elif code == b'b':
            sz = obuf.read_size()
            obj = obuf.read_bytes(sz)
        elif code == b's':
            sz = obuf.read_size()
            obj = utf8_decode(obuf.read_bytes(sz))[0]
        elif code == b'1':
            obj = obuf.read_bytes(1) == b't'
        elif code == b'i':
            sz = obuf.read_size()
            obj = int(obuf.read_bytes(sz))
        elif code == b'f':
            sz = obuf.read_size()
            obj = float(obuf.read_bytes(sz))
        elif code == b'l':
            sz = obuf.read_size()
            obj = []
            self.backrefs[br_id] = obj
            obj.extend(self._decode(obuf) for _ in range_(sz))
        elif code == b'q':
            sz = obuf.read_size()
            obj = set()
            self.backrefs[br_id] = obj
            obj.update(self._decode(obuf) for _ in range_(sz))
        elif code in (b't', b'Q'):
            cls = tuple if code == b't' else frozenset
            sz = obuf.read_size()
            obj = cls(self._decode(obuf) for _ in range_(sz))
        elif code == b'd':
            sz = obuf.read_size()
            obj = {}
            self.backrefs[br_id] = obj
            for _ in range_(sz):
                key = self._decode(obuf)
                value = self._decode(obuf)
                obj[key] = value
        elif code == b'R':
            ref_id = obuf.read_size()
            obj = self.backrefs[ref_id]
        else:
            raise ValueError('Unknown pack opcode %r' % code)

        self.backrefs[br_id] = obj
        return obj

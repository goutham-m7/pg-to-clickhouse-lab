"""Strict pgoutput v1 decoder for the one published, all-int4 relation."""
from dataclasses import dataclass, field
from io import BytesIO
import struct


@dataclass
class Batch:
    rows: list[tuple[int, ...]] = field(default_factory=list)
    commit_us: list[int] = field(default_factory=list)  # microseconds since 2000-01-01 UTC
    end: int = 0


class Message(BytesIO):
    def take(self, n):
        data = self.read(n)
        if len(data) != n:
            raise ValueError('truncated pgoutput message')
        return data

    def uint(self, n):
        return int.from_bytes(self.take(n), 'big')

    def cstr(self):
        data = self.getvalue()
        end = data.index(b'\0', self.tell())
        return self.take(end - self.tell() + 1)[:-1]

    def row(self, key_only=False):
        if self.uint(2) != 4:
            raise ValueError('unexpected tuple width')
        result = []
        for i in range(4):
            kind = self.take(1)
            if kind == b't':
                result.append(int(self.take(self.uint(4))))
            elif kind == b'n' and key_only and i:
                result.append(0)
            else:
                raise ValueError('expected non-null text int4')
        return tuple(result)


def relation(m):
    rid = m.uint(4)
    if (m.cstr(), m.cstr(), m.take(1), m.uint(2)) != (b'public', b'ledger', b'd', 4):
        raise ValueError('unexpected relation or replica identity')
    for i, name in enumerate((b'id', b'account', b'day', b'cents')):
        if (m.uint(1), m.cstr(), m.uint(4), m.uint(4)) != (int(i == 0), name, 23, 0xffffffff):
            raise ValueError('unexpected column definition')
    return rid


def decode(messages):
    batch, rid, commit = Batch(), None, None
    ordinal = 0
    for payload in messages:
        m = Message(payload)
        kind = m.take(1)
        if kind == b'B' and commit is None:
            commit = m.uint(8)
            m.take(12)  # commit time + xid
            ordinal = 0
        elif commit is None:
            raise ValueError('message outside transaction')
        elif kind == b'C':
            flags, position, end, timestamp = struct.unpack('!BQQQ', m.take(25))
            if flags or position != commit or end <= position or end <= batch.end:
                raise ValueError('invalid commit boundary')
            batch.end = end
            batch.commit_us.append(timestamp)
            commit = None
        elif kind == b'R':
            rid = relation(m)
        elif kind in (b'I', b'U', b'D') and m.uint(4) == rid:
            tag = m.take(1)
            if kind in (b'U', b'D') and tag == b'K':
                old = m.row(key_only=True)
                batch.rows.append((old[0], 0, 0, 0, (commit << 32) + ordinal, 1))
                ordinal += 1
                if kind == b'U':
                    tag = m.take(1)
            if kind in (b'I', b'U') and tag == b'N':
                batch.rows.append((*m.row(), (commit << 32) + ordinal, 0))
                ordinal += 1
            elif not (kind == b'D' and tag == b'K'):
                raise ValueError('unexpected tuple marker')
            if ordinal >= 2**32:
                raise ValueError('transaction exceeds version ordinal limit')
        else:
            raise ValueError(f'unsupported pgoutput message {kind!r} or unknown relation')
        if m.read(1):
            raise ValueError('trailing pgoutput data')
    if commit is not None:
        raise ValueError('incomplete transaction; refusing to advance slot')
    return batch

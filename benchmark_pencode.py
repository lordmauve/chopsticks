#!/usr/bin/env python

import perf

from chopsticks.pencode import pencode, pdecode


def setup():
    return [[
        1000+i,
        str(1000+i),
        42,
        42.0,
        10121071034790721094712093712037123,
        None,
        True,
        b'qwertyuiop',
        u'qwertyuiop',
        ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
        ('q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'),
        {'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'},
        frozenset(['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p']),
        {'e': 101, 'i': 105, 'o': 111, 'q': 113, 'p': 112,
         'r': 114, 'u': 117, 't': 116, 'w': 119, 'y': 121},
        ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', i],
        ('q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', i),
        {'q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', i},
        frozenset(['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', i]),
        {'e': 101, 'i': 105, 'o': 111, 'q': 113, 'p': 112,
         'r': 114, 'u': 117, 't': 116, 'w': 119, 'y': 121, 'x': i},
    ] for i in range(1000)]

runner = perf.Runner()


if __name__ == '__main__':
    v = setup()
    assert pdecode(pencode(v)) == v
    #pencode(v)
    runner.timeit(
        name='pencode',
        stmt='pencode(v)',
        globals={'v': v, 'pencode': pencode},
    )

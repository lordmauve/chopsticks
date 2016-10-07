"""A repl across hosts."""
from __future__ import print_function, unicode_literals
import ast
import sys
import readline
import traceback

PY2 = sys.version_info < (3,)

if PY2:
    from cStringIO import StringIO
else:
    from io import StringIO

if PY2:
    input = raw_input
    def exec_(code, namespace):
        exec('exec code in namespace')
else:
    exec_ = eval('exec')


def read_stmt():
    stmt = ''
    prompt = '>>> '
    indented = False
    while True:
        try:
            line = input(prompt)
        except EOFError:
            print()
            sys.exit(0)
        stmt += line + '\n'
        try:
            ast.parse(stmt)
        except SyntaxError as e:
            msg = e.args[0]
            if msg == 'unexpected EOF while parsing':
                prompt = '... '
                continue
            raise
        else:
            if line.startswith((' ', '\t')) and prompt == '... ':
                continue
            return stmt


namespace = {}


def runit(stmt):
    code = compile(stmt, '<stdin>', 'single', dont_inherit=True)
    buf = sys.stdout = StringIO()
    try:
        result = exec_(code, namespace)
    except Exception:
        return False, traceback.format_exc()
    return True, buf.getvalue()


def dorepl(group):
    from chopsticks.tunnel import ErrorResult
    from repl import runit
    try:
        stmt = read_stmt()
    except Exception:
        traceback.print_exc()
        return
    results = group.call(runit, stmt)
    vals = list(results.values())
    if all(vals[0] == v for v in vals[1:]):
        results = {'all %d' % len(vals): vals[0]}
    for host, result in sorted(results.items()):
        if isinstance(result, ErrorResult):
            success = False
            result = result.msg
        else:
            success, result = result
        color = '32' if success else '31'
        if sys.stderr.isatty():
            fmt = '\x1b[{color}m[{host}]\x1b[0m {l}'
        else:
            fmt = '[{host}] {l}'

        for l in result.splitlines():
            print(fmt.format(host=host, color=color, l=l))


if __name__ == '__main__':
    from chopsticks.tunnel import Docker
    from chopsticks.group import Group
    import chopsticks.ioloop

    chopsticks.tunnel.PICKLE_LEVEL = 2

    class Py2Docker(Docker):
        python3 = 'python2'

    group = Group([
        Py2Docker('python2.7', image='python:2.7'),
        Docker('python3.3', image='python:3.3'),
        Docker('python3.4', image='python:3.4'),
        Docker('python3.5', image='python:3.5'),
        Docker('python3.6', image='python:3.6'),
    ])

    try:
        while True:
            dorepl(group)
    finally:
        del group

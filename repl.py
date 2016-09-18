"""A repl across hosts."""
import ast
import sys
import readline
import traceback
from io import StringIO


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
    sys.stdout = StringIO()
    try:
        result = exec(code, namespace)
    except Exception:
        return False, traceback.format_exc()
    return True, sys.stdout.getvalue()


def dorepl(group):
    from chopsticks.tunnel import ErrorResult
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
    group = Group([
        Docker('python3.4', image='python:3.4'),
        Docker('python3.5', image='python:3.5'),
        Docker('python3.6', image='python:3.6'),
    ])

    try:
        while True:
            dorepl(group)
    finally:
        del group

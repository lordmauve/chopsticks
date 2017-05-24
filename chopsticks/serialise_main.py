import sys
import inspect
import types
import dis


PY2 = sys.version_info < (3,)


def trace_globals(code):
    """Find the global names loaded within the given code object."""
    LOAD_GLOBAL = dis.opmap['LOAD_GLOBAL']
    LOAD_NAME = dis.opmap['LOAD_NAME']
    global_ops = (LOAD_GLOBAL, LOAD_NAME)
    loads = set()
    for op, arg in iter_opcodes(code.co_code):
        if op in global_ops:
            loads.add(code.co_names[arg])
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            loads.update(trace_globals(c))
    return loads


def iter_opcodes(code):
    """Iterate over (op, arg) parameters in the bytecode of code.

    Taken from the code of the dis module.

    """
    if sys.version_info >= (3, 4):
        # Py3 has a function for this
        for _, op, arg in dis._unpack_opargs(code):
            yield (op, arg)
        return

    n = len(code)
    i = 0
    extended_arg = 0
    while i < n:
        c = code[i]
        op = ord(c)
        i = i + 1
        if op >= dis.HAVE_ARGUMENT:
            oparg = ord(code[i]) + ord(code[i + 1]) * 256 + extended_arg
            extended_arg = 0
            i = i + 2
            if op == dis.EXTENDED_ARG:
                extended_arg = oparg * long(65536)
            else:
                yield op, oparg


def serialise_func(f, seen=()):
    """Serialise a function defined in __main__ to be called remotely."""
    source = inspect.getsource(f)

    # We compile the source we get rather than inspecting the code object of
    # f - this captures named loaded in executing the default argument
    # expressions
    code = compile(source, '<main>', 'exec')
    names = trace_globals(code)

    imported_names = {}
    variables = {}

    fglobals = f.func_globals if PY2 else f.__globals__
    for name in names:
        try:
            v = fglobals[name]
        except KeyError:
            # Perhaps not need, or perhaps the function will crash
            continue
        if isinstance(v, types.ModuleType):
            imported_names[name] = v.__name__
        elif isinstance(v, types.FunctionType) and v.__module__ == '__main__':
            if v in seen:
                continue
            else:
                subdeps = serialise_func(v, seen=seen + (f, v,))
                vsource, _, _, vnames, vvars = subdeps
                source += '\n\n' + vsource
                imported_names.update(vnames)
                variables.update(vvars)
        else:
            variables[name] = v

    # We can't tell what submodules are used within f, but we can
    # calculate a list of submodules that have been imported, so let's send
    # that list.
    imports = set(imported_names.values())
    prefixes = tuple(mod + '.' for mod in imported_names.values())
    imports.update(mod for mod in sys.modules if mod.startswith(prefixes))

    return source, f.__name__, imports, imported_names, variables


# This module can be used as the namespace for __main__
chopmain = types.ModuleType('__chopmain__')


def deserialise_func(source, f_name, imports, imported_names, variables):
    """Deserialise a function serialised with serialise_func."""
    from __bubble__ import exec_
    ns = chopmain.__dict__

    for mod in imports:
        __import__(mod)
    ns.update(variables)
    for name, modname in imported_names.items():
        ns[name] = sys.modules[modname]
    code = compile(source, '<__chopmain__>', 'exec')
    exec_(code, ns, ns)
    return ns[f_name]


def execute_func(func_data, *args, **kwargs):
    """Execute a serialised function and return the result."""
    f = deserialise_func(*func_data)
    return f(*args, **kwargs)


def prepare_callable(func, args, kwargs):
    """Prepare a callable to be called even if it is defined in __main__."""
    if isinstance(func, types.FunctionType) and func.__module__ == '__main__':
        func_data = serialise_func(func)
        return execute_func, (func_data,) + args, kwargs
    return func, args, kwargs


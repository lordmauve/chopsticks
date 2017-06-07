import sys
import subprocess
PY2 = sys.version_info < (3,)


def check_output(*args, **kwargs):
    try:
        _check_output = subprocess.check_output
    except AttributeError:
        def _check_output(*args, **kwargs):
            """Polyfill for Python 2.6."""
            kwargs['stdout'] = subprocess.PIPE
            p = subprocess.Popen(*args, **kwargs)
            stdout, stderr = p.communicate()
            if p.returncode != 0:
                raise ValueError(
                    'subprocess exited with return code %s' % p.returncode
                )
            return stdout
    out = _check_output(*args, **kwargs)
    if not PY2:
        out = out.decode()
    return out


def output_lines(*args, **kwargs):
    """Return the lines of output from the given command args."""
    return check_output(*args, **kwargs).splitlines()

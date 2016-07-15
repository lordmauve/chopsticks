import sys
import subprocess
PY2 = sys.version_info < (3,)

try:
    check_output = subprocess.check_output
except AttributeError:
    def check_output(*args, **kwargs):
        proc = subprocess.Popen(*args, stdout=subprocess.PIPE, **kwargs)
        stdout, stderr = proc.communicate()
        if proc.returncode:
            raise IOError('Subprocess returned %d' % proc.returncode)
        return stdout



def output_lines(*args, **kwargs):
    """Return the lines of output from the given command args."""
    out = check_output(*args, **kwargs)
    if not PY2:
        out = out.decode('utf8')
    return out.splitlines()

import subprocess


def ip():
    """Get the IP of the current host."""
    lines = subprocess.check_output(['ip', '-o', 'route']).splitlines()
    for l in lines:
        ws = l.split()
        if ws[:2] == ['default', 'via']:
            return ws[2]
    return None

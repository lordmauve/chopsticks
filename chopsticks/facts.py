import re
import sys
from .helpers import output_lines


def routes():
    """Get the routing table."""
    lines = output_lines('ip -o route')
    routes = []
    for l in lines:
        ws = l.split()
        if 'linkdown' in ws:
            continue
        if ws[:2] == ['default', 'via']:
            routes.append(('%s/0' % ws[2], ws[4]))
        else:
            routes.append(ws[0], ws[2])
    return routes


def ip():
    """Get the IP of the current host."""
    lines = output_lines('ip -o address show up scope global'.split())
    for l in lines:
        ws = l.split()
        if ws[2] == 'inet':
            return re.sub(r'/\d+$', '', ws[3])
    return None


def python_version():
    """Get the Python version."""
    return list(sys.version_info)


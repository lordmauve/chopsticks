from ..helpers import output_lines


def ls(path):
    """Return a listing of a remote directory."""
    return output_lines(['ls', '-l', path])

__metaclass__ = type


class SetOps:
    """Mix-in class to provide set-like behaviour.

    Classes need only provide an _as_group() method to convert them to a
    group.

    """

    def _as_group(self):
        """Convert to a group object."""
        raise NotImplementedError()

    def _set_op(self, ano, op):
        """Perform a set operation on this group and another."""
        left = self._as_group()
        right = ano._as_group()
        cls = type(left)

        tunnels = op(set(left.tunnels), set(right.tunnels))
        grp = cls(tunnels)
        all_connection_errors = {}
        for src in [left, right]:
            all_connection_errors.update(src.connection_errors)
        for t in tunnels:
            if t.host in all_connection_errors:
                grp.connection_errors[t.host] = all_connection_errors[t.host]
        return grp

    def union(self, ano):
        """Return the union of hosts in this group and another."""
        return self._set_op(ano, set.union)

    def intersection(self, ano):
        """Return the intersection of hosts in this group and another."""
        return self._set_op(ano, set.intersection)

    def difference(self, ano):
        """Return the hosts in this group not in ano."""
        return self._set_op(ano, set.difference)

    def symmetric_difference(self, ano):
        """Return the hosts in this group not in ano."""
        return self._set_op(ano, set.symmetric_difference)

    __or__ = __add__ = union
    __and__ = intersection
    __sub__ = difference
    __xor__ = symmetric_difference

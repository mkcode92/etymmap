from collections.abc import MutableMapping


class ToDict:
    def to_dict(self):
        d = {}
        for s in self.__slots__:
            v = self.__getattribute__(s)
            if v is not None:
                d[s] = v
        return d


class NodeDictFactoryNoAttrs(MutableMapping):
    """
    We do not need to store node attributes, as these are part of the node objects themselves
    """

    def __init__(self):
        self.nodes = set()

    def __setitem__(self, node, attrs):
        self.nodes.add(node)

    def __delitem__(self, node):
        self.nodes.remove(node)

    def __getitem__(self, node):
        if node in self.nodes:
            return NoNodeAttrs()
        raise KeyError(node)

    def __len__(self):
        return len(self.nodes)

    def __iter__(self):
        return iter(self.nodes)

    def clear(self):
        self.nodes.clear()


class NoNodeAttrs(MutableMapping):
    """
    Forbid to set node attrs through the nx API
    """

    inst = None
    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        if cls.inst is None:
            cls.inst = super().__new__(cls, *args, **kwargs)
        return cls.inst

    def __setitem__(self, node, attrs):
        raise NotImplementedError

    def __delitem__(self, node):
        raise NotImplementedError

    def __getitem__(self, node):
        raise NotImplementedError

    def __len__(self):
        return 0

    def __iter__(self):
        return iter([])

    def clear(self) -> None:
        pass

    def copy(self):
        return self


class ParallelTypeDict(MutableMapping):
    """
    In a MultiDiGraph, key parallel edges by type
    """

    __slots__ = "attrs"

    def __init__(self):
        self.attrs = []

    def __setitem__(self, type_, attrs):
        if type_ == "type":
            raise ValueError
        for i, a in enumerate(self.attrs):
            if a["type"] == type_:
                self.attrs[i] = attrs
                break
        else:
            self.attrs.append(attrs)

    def __delitem__(self, type_):
        for i, c in enumerate(self.attrs):
            if c["type"] == type_:
                break
        else:
            raise KeyError(type_)
        del self.attrs[i]

    def __getitem__(self, type_):
        for c in self.attrs:
            if c["type"] == type_:
                return c
        raise KeyError(type_)

    def __len__(self):
        return len(self.attrs)

    def __iter__(self):
        return iter([a["type"] for a in self.attrs])

    def clear(self) -> None:
        self.attrs.clear()

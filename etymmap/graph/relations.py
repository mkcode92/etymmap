from collections.abc import MutableMapping

from .nodes import Node
from .relation_types import RelationType
from .utils import ToDict


class SubInfo(ToDict):
    __slots__ = ("src", "tgt")

    def __init__(self, src_template_data, tgt_template_data):
        self.src = SubNodeInfo(src_template_data)
        self.tgt = SubNodeInfo(tgt_template_data)


class SubNodeInfo(ToDict):
    __slots__ = ("language", "pos", "t")

    def __new__(cls, template_data, *args, **kwargs):
        # todo treat if sublanguage
        language = template_data.get("language")
        pos = template_data.get("pos")
        t = template_data.get("t")
        if language or pos or t:
            inst = super().__new__(cls)
            inst.language = language
            inst.pos = pos
            inst.t = t
            return inst
        return None


class DebugInfo(ToDict):
    __slots__ = ("ext_section", "ext_mechanism", "other")

    def __init__(self, ext_section, ext_mechanism, other):
        self.ext_section = ext_section
        self.ext_mechanism = ext_mechanism
        self.other = other


class RelationAttributes(ToDict, MutableMapping):
    """
    RelationAttributes stores all the edge data.
    Implements MutableMapping be used as an edge_attr_dict_factory in nx.
    """

    __slots__ = ("type", "text", "uncertain", "sub", "debug")

    def __init__(
        self,
        type: RelationType = RelationType.RELATED,
        text: str = None,
        uncertain: bool = None,
        sub: SubInfo = None,
        debug: DebugInfo = None,
    ):
        self.type = type
        self.text = text
        self.uncertain = uncertain
        self.sub = sub
        self.debug = debug

    def to_dict(self):
        d = super().to_dict()
        d["type"] = self.type.name
        return d

    def update(self, attrs: MutableMapping, **kwargs):
        for k, v in attrs.items():
            self.__setattr__(k, v)

    def __setitem__(self, name, value):
        self.__setattr__(name, value)

    def __delitem__(self, name) -> None:
        self.__delattr__(name)

    def __getitem__(self, name):
        return self.__getattribute__(name)

    def __len__(self):
        return len(self.__class__.__slots__)

    def __iter__(self):
        return iter(self.__class__.__slots__)


class Relation(ToDict):
    __slots__ = ("src", "tgt", "attrs")

    def __init__(self, src: Node, tgt: Node, attrs: RelationAttributes):
        self.src = src
        self.tgt = tgt
        self.attrs = attrs

    def to_dict(self):
        return {"src": self.src.id, "tgt": self.tgt.id, **self.attrs.to_dict()}

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"({self.src}) -{self.attrs.type.name}-> ({self.tgt})"

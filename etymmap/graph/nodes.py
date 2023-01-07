import abc
from enum import Enum
from typing import Union, List, Mapping

from .utils import ToDict

"""
Node
* LexemeBase
    * SingleMeaningStub
    * EntryLexeme
    * NoEntryLexeme
* Entity
* Phantom
"""


class Node(abc.ABC):
    __slots__ = ()

    @property
    def id(self):
        return id(self)

    def to_dict(self) -> dict:
        return {"id": hash(self)}


class LexemeBase(Node, abc.ABC):
    __slots__ = ("term", "language")

    def __init__(self, term, language):
        super().__init__()
        self.term = term
        self.language = language

    @property
    @abc.abstractmethod
    def sense_idx(self) -> int:
        pass

    @property
    def id(self):
        return self.term, self.language, self.sense_idx

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return f"{self.language}:{self.term}[{self.sense_idx}]"

    def to_dict(self):
        d = super().to_dict()
        d["term"] = self.term
        d["language"] = self.language
        d["sense_idx"] = self.sense_idx
        return d


# a placeholder, basically we just need an id
class SingleMeaningStub(LexemeBase):
    __slots__ = ()

    def __init__(self, term: str, language: str):
        super().__init__(term, language)

    @property
    def sense_idx(self) -> int:
        return 0


class Pronunciation:
    class Kind(Enum):
        plain = 0
        phonetic = 1
        phonemic = 2

    __slots__ = ("ipa", "accent", "kind")

    def __init__(
        self,
        ipa: Union[str, List[str]],
        accent: str,
        kind: Union[Kind, List[Kind]] = Kind.plain,
    ):
        self.ipa = ipa
        self.accent = accent
        self.kind = kind

    def __repr__(self):
        ipa, kind = (
            ([self.ipa], [self.kind])
            if isinstance(self.ipa, str)
            else (self.ipa, self.kind)
        )
        repr_ = [
            i
            if k == self.Kind.plain
            else f"/{i}/"
            if k == self.Kind.phonemic
            else f"[{i}]"
            for i, k in zip(ipa, kind)
        ]
        return "\n".join(
            [r + (f"({self.accent})" if self.accent else "") for r in repr_]
        )

    def to_dict(self) -> dict:
        return {
            "ipa": self.ipa,
            "accent": self.accent,
            "kind": self.kind.name
            if isinstance(self.kind, self.Kind)
            else [k.name for k in self.kind],
        }


class Gloss(ToDict):
    __slots__ = ("pos", "text", "id", "labels", "links", "tags")

    def __init__(
        self,
        pos: str,
        text: str,
        id: str = None,
        labels: List[str] = None,
        links: List[str] = None,
        tags: List[str] = None,
    ):
        self.pos = pos
        self.text = text
        self.id = id
        self.labels = labels
        self.links = links
        self.tags = tags


class NoEntryLexeme(LexemeBase):
    __slots__ = ("_sense_idx", "glosses")

    def __init__(
        self, term: str, language: str, sense_idx: int = 0, glosses: List[Gloss] = None
    ):
        super().__init__(term, language)
        self._sense_idx = sense_idx
        self.glosses = glosses

    @property
    def sense_idx(self) -> int:
        return self._sense_idx

    @classmethod
    def from_template_data(
        cls, term: str, language: str, template_data: Mapping = None, sense_idx=0
    ) -> "NoEntryLexeme":
        if template_data:
            pos, text, sense_id, labels = args = [
                template_data.get(k) for k in ["pos", "t", "id", "q"]
            ]
            glosses = (
                [Gloss(pos, text, sense_id, labels, None, None)] if any(args) else None
            )
            return cls(term, language, sense_idx=sense_idx, glosses=glosses)
        return cls(term, language)

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["has_entry"] = False
        if self.glosses:
            d["glosses"] = [g.to_dict() for g in self.glosses]
        return d


class EntryLexeme(LexemeBase):
    __slots__ = (
        "_sense_idx",
        "glosses",
        "pronunciation",
        "etymid",
        "etymology",
    )

    def __init__(
        self,
        term: str,
        language: str,
        sense_idx: int = 0,
        pronunciation: List[Pronunciation] = None,
        etymology: str = None,
        glosses: List[Gloss] = None,
        etymid: str = None,
    ):
        super().__init__(term, language)
        self._sense_idx = sense_idx
        self.pronunciation = pronunciation
        self.glosses = glosses
        self.etymid = etymid
        self.etymology = etymology

    @property
    def sense_idx(self) -> int:
        return self._sense_idx

    def to_dict(self):
        d = super().to_dict()
        if self.glosses:
            d["glosses"] = [g.to_dict() for g in self.glosses]
        if self.pronunciation:
            d["pronunciation"] = [g.to_dict() for g in self.pronunciation]
        d["etymology"] = self.etymology
        d["etymid"] = self.etymid
        d["has_entry"] = True
        return d


class Entity(Node):
    __slots__ = ("name", "occ", "nat", "born", "died", "wplink")

    def __init__(
        self,
        name: str,
        occ: str = None,
        nat: str = None,
        born: str = None,
        died: str = None,
        wplink: str = None,
        **ignore,
    ):
        self.name = name
        self.occ = occ
        self.nat = nat
        self.born = born
        self.died = died
        self.wplink = wplink

    @classmethod
    def from_template_data(cls, template_data):
        return cls(**template_data)

    def __repr__(self):
        ret = self.name
        if self.born and self.died:
            return f"{ret} ({self.born}-{self.died})"
        return ret

    @property
    def id(self):
        # this is not optimal, as incomplete information leads to different ids
        return f"{self.name}{hash((self.nat, self.born, self.died, self.wplink))}"

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["name"] = self.name
        for s in self.__class__.__slots__:
            if s:
                d[s] = getattr(self, s)
        return d


class Phantom(Node):
    def __repr__(self):
        return "?"

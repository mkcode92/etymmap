import re
from typing import Iterable, MutableMapping, Mapping, Tuple

import pymongo

from etymmap.utils import tFlexStr
from .entry_store import Query, EntryQueryBuilder, EntryStore


class MongoQuery(Query):
    __slots__ = ("filter", "selector")

    def __init__(self, filter=None, selector=None):
        self.filter = filter or {}
        self.selector = selector or {"_id": 0}

    def __repr__(self):
        return f"{self.filter}\n{self.selector}"


class MongoEntryQueryBuilder(EntryQueryBuilder):
    def __init__(self):
        self._namespaces = []
        self._titles = []
        self._sections = []
        self._languages = []
        self._filters = []
        self._selector = None

    def namespaces(self, *ns):
        self._namespaces.extend(ns)
        return self

    def title(self, title: tFlexStr = None):
        if title is None:
            return self
        if isinstance(title, str):
            self._titles.append({"title": title})
        elif isinstance(title, re.Pattern):
            self._titles.append({"title": {"$regex": title}})
        return self

    def sections(self, *sections: tFlexStr):
        self._sections.extend(sections)
        return self

    def language(self, *languages: str):
        for lang in languages:
            self._languages.append(lang)
        return self

    def filter(self, filter: Mapping = None):
        if filter:
            self._filters.append(filter)
        return self

    def selector(self, selector: Mapping = None):
        if self._selector:
            raise ValueError("Selector is already set")
        self._selector = selector
        return self

    def build(self):
        criteria = []
        criteria.extend(self._titles)
        if self._namespaces:
            criteria.append({"ns": {"$in": self._namespaces}})
        if self._languages:
            criteria.append({"language": {"$in": self._languages}})
        if self._sections:
            criteria.append(
                {
                    "sections": {  # match list[list[str]]
                        "$elemMatch": {  # match list[str]
                            "$all": [  # match str
                                {"$elemMatch": {"$regex": section}}
                                for section in self._sections
                            ]
                        }
                    }
                }
            )
        criteria.extend(self._filters)
        if len(criteria) > 1:
            filt = {"$and": criteria}
        elif len(criteria) == 1:
            filt = criteria[0]
        else:
            filt = {}
        return MongoQuery(filt, self._selector or {"_id": 0})


default_indices = (
    [("title", "hashed")],
    [("language", "hashed")],
    [("title", "hashed"), ("language", 1)],
)


class MongoEntryStore(EntryStore):
    def __init__(
        self,
        address: str,
        dbname: str,
        collection: str,
        force_fresh: bool = False,
        indices=default_indices,
        **client_kwargs,
    ):
        self.client = pymongo.MongoClient(address, **client_kwargs)
        self.db = self.client[dbname]
        self.collection = self.db[collection]
        if not self.collection.estimated_document_count() or force_fresh:
            self.clear()
            for idx in indices:
                self.collection.create_index(idx)

    @classmethod
    def from_config(cls, config: Mapping) -> "MongoEntryStore":
        return cls(**config)

    @classmethod
    def builder(cls):
        return MongoEntryQueryBuilder()

    def __contains__(self, key) -> bool:
        if not isinstance(key, Tuple):
            key = (key,)
        return (
            self.collection.find_one(
                {k: v for k, v in zip(("title", "language", "ns"), key)}
            )
            is not None
        )

    def __len__(self) -> int:
        return self.collection.estimated_document_count()

    def __iter__(self) -> Iterable[MutableMapping]:
        for entry in self.find(MongoQuery()):
            yield entry

    def add(self, entries: Iterable[MutableMapping], ordered=False) -> None:
        self.collection.insert_many(entries, ordered=ordered)

    def remove(self, query: MongoQuery) -> None:
        self.collection.remove(query.filter)

    def find(self, query: MongoQuery) -> Iterable[MutableMapping]:
        yield from self.collection.find(query.filter, query.selector)

    def clear(self):
        self.collection.drop()

    def __str__(self) -> str:
        return f"{self.__class__.__name__}[@{self.db.name}.{self.collection.name}]"

    def __repr__(self) -> str:
        return f"{self} with {len(self)} entries"

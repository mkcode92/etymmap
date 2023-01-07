import logging
import os
import random
import re
from pathlib import Path
from typing import Mapping, MutableMapping, Union, Iterable, Tuple, List, Any

import pandas as pd
import wikitextparser as wtp
from tqdm import tqdm

from etymmap.utils import FlexDict, tFlexStr
from .dump2db import dump2db, EntryConverter
from .dumps import DumpProcessor
from .store import EntryStore


class Wiktionary:
    def __init__(
        self,
        entry_store: EntryStore,
        dump_path: Union[str, Path] = None,
        force_fresh=False,
        default_namespaces=(0, 118),
    ):
        """
        An interface to wiktionary entries (i.e. pages split by languages)

        :param entry_store: an EntryStore
        :param dump_path: a path to a xml dump (can be bz2 compressed)
        :param force_fresh: override existing collection, force reparse of dump
        :param default_namespaces: the namespaces to look up
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.default_namespaces = default_namespaces
        self.entry_store = entry_store
        if dump_path and (not len(self.entry_store) or force_fresh):
            self.logger.info(
                f"Extracting {os.path.basename(dump_path)} to {self.entry_store}"
            )
            dump2db(
                self.entry_store,
                DumpProcessor(dump_path),
                EntryConverter(),
                chunksize_bytes=10**8,
            )
        self.logger.info(f"Connected to {repr(self)}")

    def __len__(self) -> int:
        return len(self.entry_store)

    def __iter__(self):
        yield from self.entry_store

    def __str__(self):
        return f"Wiktionary--{self.entry_store}"

    def __repr__(self):
        return f"{self} (~{len(self)} entries)"

    def __contains__(self, spec: Union[str, Tuple]) -> bool:
        return bool(
            list(self.entries(*self._spec2entryparams(spec), selector={"_id": 1}))
        )

    def __getitem__(self, spec: Union[str, Tuple]) -> List[Mapping]:
        res = self.entries(*self._spec2entryparams(spec))
        if res:
            return list(res)
        else:
            raise KeyError(spec)

    def _spec2entryparams(self, spec: Union[str, Tuple]):
        if isinstance(spec, str):
            return (spec,)
        elif isinstance(spec, Tuple):
            if len(spec) == 2:
                return *spec, self.default_namespaces
            else:
                return spec
        else:
            raise ValueError("Item can only specify title, lang and namespaces")

    def entries(
        self,
        title: tFlexStr = None,
        lang: Union[str, Iterable[str]] = None,
        ns: Union[int, Iterable[int]] = None,
        filter: Mapping = None,
        selector: Mapping = None,
    ) -> Iterable[Mapping]:
        ns = (
            self.default_namespaces
            if ns is None
            else (ns,)
            if isinstance(ns, int)
            else ns
        )
        lang = [] if lang is None else [lang] if isinstance(lang, str) else lang
        selector = selector or {
            "_id": 0,
            **{
                k: 1
                for k in [
                    "title",
                    "ns",
                    "language",
                    "sections",
                    "texts",
                    "_i",
                    "etym_count",
                ]
            },
        }
        query = (
            self.entry_store.builder()
            .title(title)
            .namespaces(*ns)
            .language(*lang)
            .filter(filter)
            .selector(selector)
            .build()
        )
        cursor = self.entry_store.find(query)
        if title and "_i" in selector:
            return sorted(self.entry_store.find(query), key=lambda l: l["_i"])
        return cursor

    def sections(
        self,
        *sections: tFlexStr,
        subsections: bool = False,
        title: tFlexStr = None,
        ns: Union[int, Iterable[int]] = 0,
        lang: Union[str, Iterable[str]] = None,
        filter: Any = None,
    ) -> Iterable[Tuple[List[str], str, MutableMapping]]:
        ns = (
            self.default_namespaces
            if ns is None
            else (ns,)
            if isinstance(ns, int)
            else ns
        )
        lang = [] if lang is None else [lang] if isinstance(lang, str) else lang
        select = ["title", "language", "sections", "texts", "etym_count"]
        query = (
            self.entry_store.builder()
            .title(title)
            .namespaces(*ns)
            .sections(*sections)
            .language(*lang)
            .filter(filter)
            .selector({"_id": 0, **{k: 1 for k in select}})
            .build()
        )
        lemmas = self.entry_store.find(query)
        for lemma_dct in lemmas:
            for section, section_text in zip(lemma_dct["sections"], lemma_dct["texts"]):
                if not sections:
                    is_match = True
                elif subsections:
                    is_match = all(
                        any(re.match(p, s) for s in section) for p in sections
                    )
                else:
                    is_match = any(re.match(p, section[-1]) for p in sections)
                if is_match:
                    yield section, section_text, lemma_dct

    def templates(
        self,
        *sections: tFlexStr,
        template_types: Iterable[tFlexStr] = None,
        get_context: bool = False,
        buffer_size: int = 50,
        **section_kwargs,
    ) -> Iterable[
        Union[wtp.Template, Tuple[wtp.Template, List[str], str, MutableMapping]]
    ]:
        """
        Iterate over (wtp-) templates

        :param template_types: Restrict template names
        :param get_context: Also return section and context information
        :param buffer_size: If get_context is false, concatenate section texts to save resources at parsing
        :param section_kwargs: other parameters for self.sections
        :return: Iterable of templates or tuples of templates and context
        """
        template_types = (
            FlexDict({t: 1 for t in template_types}) if template_types else None
        )

        def get_templates():
            for t in wtp.parse(section_text).templates:
                if not template_types or (t.name.strip() in template_types):
                    if get_context:
                        yield t, section, section_text, ctx_lemma
                    else:
                        yield t

        buffer = []  # buffering speeds up template-only-retrieval (a bit)
        for i, (section, section_text, ctx_lemma) in enumerate(
            self.sections(*sections, **section_kwargs)
        ):
            if not get_context and buffer_size:
                buffer.append(section_text)
                if len(buffer) < buffer_size:
                    continue
                else:
                    section_text = "\n".join(buffer)
                    buffer.clear()
            yield from get_templates()
        if buffer:
            section_text = "\n".join(buffer)
            yield from get_templates()

    def export_index(
        self,
        columns=("title", "language", "ns", "etym_count"),
        index=("title", "language"),
        drop_duplicates=True,
        **kwargs,
    ):
        data = iter(
            tqdm(
                (
                    (e["title"], e["language"], e["ns"], e["etym_count"])
                    for e in self.entries()
                ),
                total=len(self),
                unit=" entries",
            )
        )
        ret = pd.DataFrame.from_records(data, columns=columns)
        ret.language = ret.language.astype("category")
        ret.ns = ret.ns.astype("uint8")
        ret.etym_count = ret.etym_count.astype("uint8")
        ret.set_index(list(index), inplace=True)
        if drop_duplicates:
            ret = ret[~ret.index.duplicated(keep="first")]
        return ret

    def sample(self, n=1000, head=None, random_seed=117) -> Iterable[MutableMapping]:
        random.seed(random_seed)
        indices = set(random.sample(range(head or len(self)), n))
        break_ = max(indices)
        for i, e in enumerate(self):
            if i in indices:
                yield e
            if i > break_:
                break

import abc
import os
import warnings
from pathlib import Path
from typing import List, Iterable, Tuple, Union

from etymmap.specific import Specific
from etymmap.utils import SectionText
from .dumps import raw2json, DumpProcessor
from .store.entry_store import EntryStore


class Converter:
    def convert_chunk(self, raw_pages: List[bytes]) -> List[dict]:
        return [page for raw_page in raw_pages for page in self.convert(raw_page)]

    @abc.abstractmethod
    def convert(self, raw_page: bytes) -> Iterable[dict]:
        pass


class EntryConverter(Converter):
    def __init__(self, ignore_noheading=True):
        self.ignore_noheading = ignore_noheading

    def convert(
        self,
        raw_page,
    ):
        """
        Entry-oriented: one document for each lemma
        """
        json_page = raw2json(raw_page)
        rev = json_page["revision"][0]
        text = rev["text"]
        sections = SectionText(text, Specific.entry_parser.parse_section(text))
        ret = []
        title, ns = json_page["title"], json_page["ns"]
        title = Specific.entry_parser.clean_title(title, ns)
        base_entry = {"title": title, "ns": json_page["ns"]}
        for i, ((lang,), subsections) in enumerate(sections.by_lvl(0)):
            try:
                lang_id = Specific.language_mapper.name2code(lang)
            except KeyError:
                lang_id = Specific.language_mapper.UNKNOWN_LANGUAGE
            sss, texts = zip(*subsections)
            if self.ignore_noheading and sss == ([Specific.entry_parser.NO_HEADING],):
                continue
            ret.append(
                {
                    **base_entry,
                    "_i": i,  # to reconstruct order
                    "language": lang_id,
                    "sections": list(sss),
                    "texts": list(texts),
                    "etym_count": Specific.entry_parser.count_etymologies(sss, []),
                }
            )
        if not (ret or self.ignore_noheading):
            warnings.warn(
                f"Could not extract page {json_page['title']}:\n{rev['text']}"
            )
            ret = [
                {
                    **base_entry,
                    "_i": 0,
                    "language": Specific.language_mapper.UNKNOWN_LANGUAGE,
                    "sections": [[Specific.entry_parser.NO_HEADING]],
                    "texts": [rev["text"]],
                    "etym_count": 0,
                }
            ]
        return ret


class PageConverter(Converter):
    def get_spans_and_sections_from_revision(self, revision):
        sections = SectionText(
            revision["text"], Specific.entry_parser.parse_section(revision["text"])
        )
        try:
            sections, spans = zip(*sections.iterspans())
        except ValueError:
            return [], []
        return list(sections), list(spans)

    def convert(self, raw_page):
        """
        Page-oriented: one document for each page (single revision)
        """
        json_page = raw2json(raw_page)
        rev = json_page["revision"][0]
        sections, spans = self.get_spans_and_sections_from_revision(rev)
        rev["sections"] = sections
        rev["spans"] = spans
        # get all revision predicates one level up
        rev["rev_id"] = rev["id"]
        del rev["id"]
        if "parentid" in rev:
            rev["rev_parentid"] = rev["parentid"]
            del rev["parentid"]
        json_page.update(rev)
        del json_page["revision"]
        return json_page


def dump2db(
    store: EntryStore,
    dump_processor: DumpProcessor,
    converter: Converter,
    chunksize_bytes: int,
    **kwargs,
):
    for entries in dump_processor.apply(
        converter.convert_chunk, chunksize_bytes=chunksize_bytes, **kwargs
    ):
        store.add(entries, ordered=False)


def db_and_collection_by_filename(dump_path: Union[str, Path]) -> Tuple[str, str]:
    """
    e.g. enwiktionary-20000101-pages-articles.xml -> enwiktionary, 20000101
    """
    return tuple(os.path.basename(Path(dump_path)).split("-")[:2])

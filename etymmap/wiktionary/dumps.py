import bz2
import io
import multiprocessing as mp
import warnings
from pathlib import Path
from typing import Union, Mapping, Any, Iterable, Set, List, Callable

import lxml.etree
import pandas as pd

from etymmap.utils import wrap_with_progressbar

PAGE_START = b"  <page>"
PAGE_END = b"  </page>"
REV_START = b"    <revision>"
REV_END = b"    </revision>"
CLOSE_PAGE = b"    </revision>\n  </page>\n"
PARTIAL = b"    <partial/>"

# types of the xml elements
TYPE_MAPPING = {
    "minor": bool,
    "partial": bool,
    "id": int,
    "parentid": int,
    "ns": int,
    "timestamp": pd.to_datetime,
}

REPEATED_TAGS = {"revision"}


def raw2xml(raw_page: bytes) -> lxml.etree.ElementBase:
    """
    Parse a raw page to xml
    """
    return lxml.etree.parse(
        io.BytesIO(raw_page), parser=lxml.etree.XMLParser(huge_tree=True)
    ).getroot()


def xml2json(
    elem: lxml.etree.ElementBase,
    repeated_tags: Set[str] = None,
    type_mapping: Mapping = None,
):
    """
    Convert xml elements to (json) dictionaries.

    :param elem: the lxml element to be converted
    :param repeated_tags: tags
    :param type_mapping: a mapping from tag names to types. Defaults to dumps.TYPE_MAPPING
    :return: a dictionary (json-dumpable)
    """
    repeated_tags = REPEATED_TAGS if repeated_tags is None else set()
    type_mapping = TYPE_MAPPING if type_mapping is None else {}
    ret = {}
    for child in elem:
        tag = child.tag
        child_json = xml2json(child)
        if tag in ret:
            try:
                ret[tag].append(child_json)
            except AttributeError:
                ret[tag] = [ret[tag], child_json]
        elif tag in repeated_tags:
            ret[tag] = [child_json]
        else:
            ret[tag] = child_json
    if not ret:
        type_ = type_mapping.get(elem.tag, str)
        value = elem.text
        if not value and type_ is bool:
            return True
        return type_(value)
    return ret


def raw2json(raw_page, *args, **kwargs):
    return xml2json(raw2xml(raw_page), *args, **kwargs)


class DumpProcessor:
    def __init__(self, path: Union[str, Path], decompress: bool = False):
        self.path = path
        self.decompress = decompress or path.endswith(".bz2")

    def sized_chunks(
        self,
        max_byte_size_per_chunk: int = 10**8,
        head: int = None,
        progress: bool = None,
    ):
        pages = []
        pages_size = 0
        for page in wrap_with_progressbar(self.raw_pages(head=head), progress):
            page_size = len(page)
            if pages_size + page_size > max_byte_size_per_chunk:
                yield pages
                pages = [page]
                pages_size = page_size
            else:
                pages.append(page)
                pages_size += page_size
        if pages:
            yield pages

    def raw_pages(
        self, head: int = None, split_revisions_over: int = 50 * 10**6
    ) -> Iterable[bytes]:
        """
        The byte strings of the single pages of the dump.
        It is assumed that the dump follows the well
        ! The entire dump is scanned, so it might take long !
        """
        current_page = bytearray()
        inpage = end = False
        split_at_next_revision = False
        npages = 0
        with (
            bz2.BZ2File(self.path, "rb") if self.decompress else open(self.path, "rb")
        ) as src:
            for line in src:
                if line.startswith(PAGE_START):
                    inpage = True
                elif line.startswith(PAGE_END):
                    end = True
                elif split_at_next_revision and line.startswith(REV_END):
                    split_at_next_revision = False
                    current_page.extend(CLOSE_PAGE)
                    page = bytes(current_page)
                    yield page
                    current_page = bytearray(page[: page.find(REV_START)] + PARTIAL)
                    continue
                if inpage:
                    current_page.extend(line)
                    if (
                        not split_at_next_revision
                        and len(current_page) > split_revisions_over
                    ):
                        split_at_next_revision = True
                if end:
                    yield bytes(current_page)
                    npages += 1
                    if head and npages >= head:
                        return
                    current_page = bytearray()
                    inpage = end = False

        if current_page:
            warnings.warn("Unclosed page at end of dump.")

    def apply(
        self,
        f: Callable[[Union[bytes, List[bytes]]], Any],
        chunksize_bytes: int = None,
        head: int = None,
        progress: Union[bool, dict] = False,
        mp_processes: int = max(1, mp.cpu_count() - 1),
        mp_maxtasksperchild: int = None,
        mp_chunk_size: int = 1,
    ) -> Iterable:
        """
        Apply a function to all pages in dump

        If chunk_size_bytes is set, the pages are passed as a list to f.
        Otherwise, single pages are passed.

        :return: Iterable of applying f to the pages / page chunks
        """
        if chunksize_bytes:
            raw_pages_iter = self.sized_chunks(
                chunksize_bytes, head=head, progress=progress
            )
        else:
            raw_pages_iter = wrap_with_progressbar(
                self.raw_pages(head=head), progress=progress
            )
        if mp_processes > 1:
            with mp.Pool(
                processes=mp_processes, maxtasksperchild=mp_maxtasksperchild
            ) as pool:
                yield from pool.imap_unordered(
                    f, raw_pages_iter, chunksize=mp_chunk_size
                )
        else:
            for raw_page in raw_pages_iter:
                yield f(raw_page)

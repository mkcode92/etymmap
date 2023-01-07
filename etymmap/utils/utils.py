import itertools
import re
from collections.abc import MutableMapping
from typing import Iterator, Any, Tuple, List, Union

import wikitextparser as wtp
from tqdm import tqdm

WIKILINK = re.compile(r"\[\[([a-z]+:)?(?:[^]|]*\|)?([^]|]*)]]")
WIKITEMPLATE = re.compile(r"{{([^}{]*)}}")
WIKIFORMATTING = re.compile(r"('+)((?:[^']|\\')*)\1")

tFlexStr = Union[str, re.Pattern]
tMaybeParsed = Union[str, wtp.WikiText]
tMaybeTemplate = Union[str, wtp.Template]


def wrap_with_progressbar(iterable, progress=None):
    if progress:
        if isinstance(progress, dict):
            return tqdm(iterable, **progress)
        return tqdm(iterable)
    return iterable


def quick_plaintext(t: str) -> str:
    return strip_wikitemplate(strip_wikilink(t))


def strip_wikilink(t: str) -> str:
    return re.sub(WIKILINK, r"\2", t or "")


def strip_wikitemplate(t: str) -> str:
    return re.sub(WIKITEMPLATE, r"\1", t or "")


def rm_wikitemplate(t: str) -> str:
    return re.sub(WIKITEMPLATE, r"", t or "")


def strip_formatting(t: str) -> str:
    """
    Strip bold and italics
    """
    return re.sub(WIKIFORMATTING, r"\2", t or "")


def make_parsed_subsection(orig: wtp.WikiText, start, end=None):
    """
    This is a hack to allow selection of *parsed* subspans

    :param orig: the original element
    :param start, end: the new start/end relative to orig
    """
    o_start, o_end = orig.span
    if start >= 0:
        start += o_start
    else:
        start += o_end
    if end is not None:
        if end >= 0:
            end += o_start
        else:
            end += o_end
    else:
        end = o_end
    # Section delegates to SubWikiText, which is what we actually want here
    return wtp.Section(
        orig._lststr,
        orig._type_to_spans,
        [start, end, None, None],  # this is a bit risky, as we rely on unused bytearray
        "SubWikiText",
    )


def nonoverlapping(
    wikitexts: List[wtp.WikiText],
) -> Tuple[List[wtp.WikiText], List[bool]]:
    """
    Drop nested templates/ links
    """
    # sort by start, prefer longer spanning elements (basically, ignore nested structures)
    wikitexts = sorted(wikitexts, key=lambda i: (i.span[0], -i.span[1]))
    ret = []
    recursive = []
    for i, t in enumerate(wikitexts):
        if not ret or ret[-1].span[1] <= t.span[0]:
            ret.append(t)
            recursive.append(False)
        else:
            recursive[-1] = True
    return ret, recursive


class FlexDict(MutableMapping):
    def __init__(self, *args, **kwargs):
        """
        A special dict that can map either str or regex to a value.
        In particular a string maps to a value iff it is contained as a string key
        or any pattern key matches the string
        """
        self._by_string = {}
        self._by_pattern = {}
        self.update(dict(*args, **kwargs))

    def __setitem__(self, k: tFlexStr, v: Any) -> None:
        if isinstance(k, str):
            self._by_string.__setitem__(k, v)
        elif isinstance(k, re.Pattern):
            self._by_pattern.__setitem__(k, v)

    def __delitem__(self, v: tFlexStr) -> None:
        if isinstance(v, str):
            self._by_string.__delitem__(v)
        elif isinstance(v, re.Pattern):
            self._by_pattern.__delitem__(v)

    def __getitem__(self, k: tFlexStr) -> Any:
        if isinstance(k, re.Pattern):
            return self._by_pattern[k]
        try:
            return self._by_string[k]
        except KeyError:
            for p, v in self._by_pattern.items():
                if p.fullmatch(k):
                    return v
            raise KeyError(k)

    def __contains__(self, k):
        return (k in self._by_string) or (k in self._by_pattern)

    def __len__(self) -> int:
        return len(self._by_string) + len(self._by_pattern)

    def __iter__(self) -> Iterator[tFlexStr]:
        return itertools.chain(self._by_string, self._by_pattern)


class Equivalent:
    def __init__(self, *args, **kwargs):
        """
        A structure to handle equivalent sets

        :param args, kwargs: same parameters as for dict creation, representing a mapping from names to representatives
        """
        self._map = FlexDict()
        self._representatives = set()
        for repr, others in dict(*args, **kwargs).items():
            self.declare(repr, *others)

    def declare(
        self,
        representative: str,
        *others: tFlexStr,
        add=False,
        force=False,
        add_lower=False,
    ):
        """
        :param representative: the representative of the equivalence class
        :param others: other names of the class
        :param add: if false, check representative is unused
        :param force: if false, check value is unused
        :param add_lower: automatically add lowercase forms
        """
        for e in [representative, *others]:
            if e in self._map:
                if e is representative:
                    if not add:
                        raise ValueError(
                            f"Representative {representative} already in use"
                        )
                elif not force and self._map[e] != representative:
                    raise ValueError(f"Element {e} already in use")
            self._map[e] = representative
            if add_lower and isinstance(e, str):
                self._map[e.lower()] = representative
        self._representatives.add(representative)

    def __contains__(self, e: str):
        return self.get(e) is not None

    def __getitem__(self, e: str):
        return self._map[e]

    @property
    def map(self):
        return dict(self._map)

    def get(self, e: str, default=None):
        return self._map.get(e, default)

    def group(self, e: str):
        rep = self._map[e]
        return {k for k, r in self._map.items() if r == rep}

    def __delitem__(self, e: tFlexStr):
        if e in self._representatives:
            self._representatives.remove(e)
            for e in self.group(e):
                del self._map[e]
        else:
            del self._map[e]

    def __iter__(self) -> Iterator[str]:
        return iter(self._representatives)


def get_items(wlist: wtp.WikiList, avoid_reparse=True) -> List[wtp.WikiText]:
    """
    Gets first-level items from a wikilist

    :param wlist:
    :param avoid_reparse:
    :return:
    """
    if avoid_reparse:
        # this does not work as intended :(
        items = []
        append = items.append
        match = wlist._match
        ms = match.start()
        subspan = make_parsed_subsection
        for s, e in match.spans("item"):
            # Section uses subwikitext internally
            append(subspan(wlist, s - ms, e - ms))
        return items
    else:
        return [wtp.parse(item) for item in wlist.items]


link_types = {
    "Image",
    "File",
    "Category",
    "Reconstruction",
    "s",
    "Appendix",
    "Thesaurus",
    "q",
}


def analyze_link_target(target: str, _wikipedia=re.compile("(w(ikipedia)?)", re.I)):
    """
    in wikilinks and link parameters in templates, parse the (prefix:)?title(#anchor)? - component

    :return (text, anchor, prefix)
    """
    s = target.split("#")
    if len(s) == 2:
        title, anchor = s
    else:
        title, anchor = target, None
    title_parts = title.split(":")
    if len(title_parts) > 1:
        if _wikipedia.fullmatch(title_parts[0]):
            text = title_parts[-1]
            special = "wikipedia"
        elif (title_parts[0] or title_parts[1]) in link_types:
            extra_colon = 1 if title_parts[0] else 2
            text = "".join(title_parts[extra_colon:])
            special = title_parts[extra_colon - 1]
        # ignore images, files, interwiki links
        else:
            text, special = title, None
    else:
        text, special = title, None
    return text, anchor, special

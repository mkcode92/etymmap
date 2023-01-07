import warnings
from typing import Iterable, Tuple, List, Any, Union

import wikitextparser as wtp

from .utils import tMaybeParsed, make_parsed_subsection


class SeqMap:
    """
    A nested dict, whose values can be addressed using multiple keys,
    e.g. section[['English', 'Adjective', 'Etymology']]
    """

    # the value marker
    _vkey = object()

    def __init__(self):
        self.d = {}

    @classmethod
    def from_items(cls, items):
        """
        This is not efficient, but simple

        :param items:
        :return:
        """
        ret = cls()
        for k, v in items:
            ret[k] = v
        return ret

    def __getitem__(self, keys) -> Any:
        if isinstance(keys, list):
            d = self.d
            for i, key in enumerate(keys):
                try:
                    d = d[key]
                except KeyError:
                    raise KeyError(f"{keys} at {i}")
        else:
            d = self.d[keys]
        return d.get(self._vkey, d)

    def __setitem__(self, keys, value: Any) -> None:
        if isinstance(keys, str):
            keys = [keys]
        elif isinstance(value, dict):
            warnings.warn("Setting values of type dict can have unexpected semantics")
        d = self.d
        for i, key in enumerate(keys):
            try:
                d = d[key]
            except KeyError:
                for k in keys[i:]:
                    d[k] = newd = {}
                    d = newd
                break
        d[self._vkey] = value

    def _items(self, d: dict) -> Iterable[Tuple[List[str], Any]]:
        for k, v in d.items():
            if k is self._vkey:
                yield [], v
            if isinstance(v, dict):
                for sec, val in self._items(v):
                    yield [k, *sec], val

    def items(self) -> Iterable[Tuple[List[str], Any]]:
        return self._items(self.d)

    def keys(self) -> Iterable[List[str]]:
        for k, _ in self.items():
            yield k

    def values(self) -> Iterable[Any]:
        for _, v in self.items():
            yield v

    def __iter__(self) -> Iterable[List[str]]:
        return self.keys()


class SectionText:
    def __init__(self, text: tMaybeParsed, seq_map: SeqMap):
        """
        Gives access to sections of a wikitext
        """
        self.text = text
        self.sections = seq_map

    def __iter__(self):
        return self.sections.keys()

    def by_lvl(
        self, lvl: int = 0
    ) -> Iterable[Tuple[str, List[Tuple[List[str], Union[wtp.WikiText, str]]]]]:
        group = []
        pref_up_to_lvl = []
        for section, text in self.iteritems():
            secpref = section[: lvl + 1]
            if pref_up_to_lvl[: len(secpref)] != secpref:
                if group:
                    yield pref_up_to_lvl, group
                    group.clear()
                pref_up_to_lvl = secpref
            group.append((section, text))
        if group:
            yield pref_up_to_lvl, group

    def section_text(self, key) -> Union[wtp.WikiText, str]:
        """
        Get the (wiki-)text that is in the scope of the section with name <key>
        """
        return self.getspan(*self.sections[key])

    def getspan(self, start, end) -> Union[wtp.WikiText, str]:
        if isinstance(self.text, str):
            return self.text[start:end]
        else:
            return make_parsed_subsection(self.text, start, end)

    def iteritems(self) -> Iterable[Tuple[List[str], Union[wtp.WikiText, str]]]:
        """
        Iterate over all pairs of (section, text)
        """
        for section, (start, end) in self.sections.items():
            yield section, self.getspan(start, end)

    def iterspans(self) -> Iterable[Tuple[List[str], Tuple[int, int]]]:
        yield from self.sections.items()

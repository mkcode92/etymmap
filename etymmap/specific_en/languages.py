import ast
import importlib.resources
import io
import json
import logging
import re
import unicodedata
import warnings
from collections import defaultdict, Counter
from typing import List, Mapping, Union, Set

import lxml.etree
import networkx as nx
import pandas as pd
import requests

from etymmap.specific import LanguageDataUpdaterABC, LanguageMapperABC
from etymmap.specific_en import consts

logger = logging.getLogger("LanguageResources")


class CachedLanguageDataUpdater(LanguageDataUpdaterABC):
    def make_language_data(self) -> Mapping[str, Mapping]:
        return json.loads(
            importlib.resources.read_text(
                "etymmap.data", "language_data.json", encoding="utf-8"
            )
        )

    def make_family_data(self) -> Mapping[str, Mapping]:
        return json.loads(
            importlib.resources.read_text(
                "etymmap.data", "language_families.json", encoding="utf-8"
            )
        )


class OnlineLanguageDataUpdater(LanguageDataUpdaterABC):
    """
    This class updates the language data needed for code/name mapping and term normalization (diacritics removal)
    You may override methods of this class to get a better extraction
    """

    def make_language_data(self) -> dict:
        """
        Collects data both from the tables and the data modules

        :return: a json mapping language codes to language data
        """
        language_data = self.get_language_tables_data()
        language_data.update(self.get_special_language_data())
        normalizations = self.get_normalization_data()
        for lang, langdata in language_data.items():
            if lang in normalizations:
                if langdata.get("Diacr?") == "":
                    logger.warning(
                        f"Extracted diacr. normalization where (maybe) unnecessary: {lang}"
                    )
                langdata["normalization"] = normalizations[lang]
            elif langdata.get("Diacr?"):
                logger.warning(f"Missed to extract diacr. normalization for {lang}")
        s = set(normalizations) - set(language_data)
        if s:
            logger.warning(f"Extracted diacr. normalization for unknown languages {s}")
        for ldata in language_data.values():
            self._clean(ldata)
        return language_data

    def _clean(self, ldata):
        ldata["Canonical name"] = ldata["Canonical name"].strip()
        ldata["Other names"] = [
            n.strip() for n in ldata["Other names"].split(",") if n.strip()
        ]

    def make_family_data(self) -> Mapping[str, Mapping]:
        tables = pd.concat(pd.read_html(consts.LANGUAGE_FAMILIES))
        data = tables.fillna("").set_index("Code").to_dict(orient="index")
        for code, ldata in data.items():
            self._clean(ldata)
            if ldata["Parent family"] == "not a family":
                ldata["Parent family"] = None
        return data

    @staticmethod
    def read_online_lang_table(path):
        resp = requests.get(path, timeout=2)
        resp.raise_for_status()
        parsed = lxml.etree.parse(io.BytesIO(resp.content))
        subtables = [
            pd.read_html(
                io.BytesIO(lxml.etree.tostring(t)), na_values="", keep_default_na=False
            )[0]
            for t in parsed.findall("//table[@class='wikitable sortable mw-datatable']")
        ]
        return subtables

    def get_language_tables_data(self) -> dict:
        language_tables = self.read_online_lang_table(consts.LANGUAGE_TABLES)
        return (
            pd.concat(language_tables)
            .fillna("")
            .set_index("Code")
            .to_dict(orient="index")
        )

    def get_special_language_data(self) -> dict:
        ret = {}
        special_language_tables = self.read_online_lang_table(
            consts.SPECIAL_LANGUAGE_TABLES
        )
        for type_, table in zip(
            ["reconstructed", "constructed", "sort/diacr", "meta", "etym-only"],
            special_language_tables,
        ):
            if type_ in ["sorts/diacr", "meta"]:
                continue
            if type_ in ["reconstructed", "constructed"]:
                df = table.set_index("Code").fillna("")
                df["type"] = type_
                ret.update(df.to_dict(orient="index"))
            if type_ == "etym-only":
                table["Codes"] = table["Codes"].apply(
                    lambda x: [c.strip() for c in x.split(",")]
                )
                table = (
                    table.explode("Codes")
                    .rename(columns={"Codes": "Code"})
                    .set_index("Code")
                    .fillna("")
                )
                table["type"] = type_
                ret.update(table.to_dict(orient="index"))
        return ret

    def get_normalization_data(self):
        """
        Parses the diacritics replacements out of the lua codes
        """
        data = {}
        for ld in consts.LANGUAGE_DATA_MODULES:
            resp = requests.get(ld)
            if resp.content:
                lang_data_code = self.get_code_from_html(resp.content.decode("utf-8"))
                data.update(self.extract_data(lang_data_code))
        return data

    @staticmethod
    def get_code_from_html(content: str) -> str:
        def unpack_text(e, collector=None):
            collector = [] if collector is None else collector
            if e.text:
                collector.append(e.text.strip())
            for c in e:
                unpack_text(c, collector)
            return collector

        tree = lxml.etree.fromstring(content, parser=lxml.etree.HTMLParser())
        preformatted_code = tree.findall(".//pre")
        if not len(preformatted_code) == 1:
            warnings.warn("Unexpected other code elements in language data page")
        return "".join(unpack_text(preformatted_code[0]))

    @staticmethod
    def extract_data(lang_data_code):
        ret = {}
        diacr = dict(
            DOUBLEINVBREVE="\u0361",
            GRAVE="\u0300",
            ACUTE="\u0301",
            CIRCUMFLEX="\u0302",
            CIRC="\u0302",
            TILDE="\u0303",
            MACRON="\u0304",
            OVERLINE="\u0305",
            BREVE="\u0306",
            DOTABOVE="\u0307",
            DIAER="\u0308",
            CARON="\u030C",
            DGRAVE="\u030F",
            INVBREVE="\u0311",
            DOTBELOW="\u0323",
            RINGBELOW="\u0325",
            CEDILLA="\u0327",
            OGONEK="\u0328",
            CGJ="\u034F",
            UNDERTIE="\u035c",
        )
        diacr_expr = re.compile(f"({'|'.join(diacr)})")
        # this simplifies the other expressions a lot
        lang_data_code = re.sub(r"\s*=\s*", "=", lang_data_code)
        # match the m["lang"]=data snippets, strip code preambel
        data_items = re.split(r"m\[\"([^\"]+)\"]=", lang_data_code)[1:]
        for i, name in enumerate(data_items[::2]):
            if name in ["gmq-oda", "gmq-osw"]:
                # :( exeptional encoding
                ret[name] = {
                    "replace_from": [
                        "Ā",
                        "ā",
                        "Ē",
                        "ē",
                        "Ī",
                        "ī",
                        "Ō",
                        "ō",
                        "Ū",
                        "ū",
                        "Ȳ",
                        "ȳ",
                        "Ǣ",
                        "ǣ",
                        diacr["MACRON"],
                    ],
                    "replace_to": [
                        "A",
                        "a",
                        "E",
                        "e",
                        "I",
                        "i",
                        "O",
                        "o",
                        "U",
                        "u",
                        "Y",
                        "y",
                        "Æ",
                        "æ",
                    ],
                    "remove_diacritics": "",
                }
                continue
            params = data_items[2 * i + 1]
            m = re.match(
                r".*?entry_name="
                r"{"
                r"(?:"
                r"from={(?P<from>[^}]+)}"
                r"|"
                r"to={(?P<to>[^}]*)}"
                r"|"
                r"remove_diacritics=(?P<rmd>[^,^}]+)"
                r"|.*?)+"
                r"}",
                params,
            )
            if m:
                groups = [m.group("from"), m.group("to"), m.group("rmd")]
                for j, g in enumerate(groups):
                    if g:
                        # replace unicode reprs by their quoted letters
                        g = re.sub(
                            r"u\(0x([\da-fA-F]+)\)",
                            lambda m: f'"{chr(int(m.group(1), 16))}"',
                            g,
                        )
                        # replace diacritics variables by their quoted letters
                        g = re.sub(diacr_expr, lambda d: f'"{diacr[d.group(1)]}"', g)
                        # join strings at lua joiners ("a".."b" -> "a""b", but ast converts to "ab")
                        g = "".join(re.split(r"[^.]\.\.[^.]", g))
                        try:
                            if j < 2:
                                params = ast.literal_eval("[" + g + "]")
                            else:
                                params = ast.literal_eval(g)
                        except Exception as e:
                            # :( exceptional syntax for 'tru'
                            if g == '"[(0x0711,0x0730,("-"):byte(),0x074A]"':
                                params = ["[\u0711\u0730-\u074a]"]
                            else:
                                warnings.warn(
                                    f"Could not extract  diacritics info for {name}: {e} ({g})"
                                )
                                params = [] if j < 2 else ""
                    else:
                        params = [] if j < 2 else ""
                    groups[j] = params
                ret[name] = {
                    "replace_from": groups[0],
                    "replace_to": groups[1],
                    "remove_diacritics": groups[2],
                }
            elif "entry_name" in params:
                logger.warning(
                    f"Could not extract diacritics info for {name}: Pattern not matched ({params})"
                )
        return ret


class Normalization:
    def __init__(
        self,
        remove_diacritics: str = None,
        replace_from: List[str] = None,
        replace_to: List[str] = None,
    ):
        """
        Maps a term as used by a template to a normalized form that is used by a page title

        :param remove_diacritics: delete these diacritics in the unicode decomposition
        :param replace_from: replace these characters/ character sets...
        :param replace_to: ...by these characters
        """

        self.rm_diacritics_table = (
            str.maketrans("", "", remove_diacritics) if remove_diacritics else None
        )
        character_replacements_from = []
        character_replacements_to = []
        self.complex_replacements = []
        self.complex_deletions = []
        for (from_, to) in zip(replace_from, replace_to):
            if len(from_) == 1 and len(to) == 1:
                character_replacements_from.append(from_)
                character_replacements_to.append(to)
            else:
                self.complex_replacements.append((re.compile(from_), to))
        deletions = replace_from[len(replace_to) :]
        simple_deletions = []
        for d in deletions:
            if len(d) == 1:
                simple_deletions.append(d)
            else:
                self.complex_deletions.append(d)
        self.translation_table = str.maketrans(
            *[
                "".join(c)
                for c in [
                    character_replacements_from,
                    character_replacements_to,
                    simple_deletions,
                ]
            ]
        )


class LanguageMapper(LanguageMapperABC):
    unknown_codes = Counter()

    def __init__(self, updater=CachedLanguageDataUpdater()):
        # code -> ldata
        self._language_data = updater.make_language_data()
        # code -> ldata
        self._family_data = updater.make_family_data()
        # name -> [lang_codes], [family_codes]
        self._names2code = self.make_name_map()
        self.normalizations = {
            lang: Normalization(**v)
            for lang, v in self.get_normalization_data().items()
        }

    def __contains__(self, code: str) -> bool:
        return code in self._language_data or (code in self._family_data)

    @property
    def codes(self) -> Set[str]:
        return set(self._language_data).union(self._family_data)

    @property
    def names(self) -> Set[str]:
        return set(self._names2code)

    @property
    def canonical_names(self) -> List[str]:
        return [
            v["Canonical name"]
            for v in set(self._language_data.values()).union(self._family_data.values())
        ]

    def make_name_map(self) -> Mapping[str, List[str]]:
        """
        Map names to codes
        """
        collector = defaultdict(lambda: (set(), set()))
        for idx, data in enumerate([self._language_data, self._family_data]):
            for code, ldata in data.items():
                cname, onames = ldata["Canonical name"], ldata["Other names"]
                collector[cname][idx].add(code)
                for name in onames:
                    collector[name][idx].add(code)
        return {k: [list(v) for v in vs] for k, vs in collector.items()}

    def code2name(self, code: str) -> str:
        if code is self.UNKNOWN_LANGUAGE:
            raise KeyError(f"Unknown code: {code}")
        try:
            return self._language_data[code]["Canonical name"]
        except KeyError:
            try:
                return self._family_data[code]["Canonical name"]
            except KeyError:
                raise KeyError(f"Unknown code: {code}")

    def name2code(
        self,
        name: str,
        prefer_detailed=True,
        prefer_language=True,
        allow_ambiguity=False,
    ) -> Union[str, List[str]]:
        name = name.strip()
        try:
            language_codes, family_codes = self._names2code[name]
        except KeyError:
            raise KeyError(f"Unknown language name {name}")

        all_codes = language_codes + family_codes
        if allow_ambiguity:
            return all_codes

        if len(all_codes) == 1:
            return all_codes[0]

        # prefer canonical names
        for codes, data in [
            (language_codes, self._language_data),
            (family_codes, self._family_data),
        ]:
            for code in codes:
                if data[code]["Canonical name"] == name:
                    return code

        if language_codes:
            all_codes = []
            if prefer_detailed:
                for c in language_codes:
                    if self._language_data[c].get("Family"):
                        all_codes.append(c)
            if not all_codes:
                all_codes.extend(language_codes)
            if not prefer_language:
                all_codes.extend(family_codes)
            if len(all_codes) == 1:
                return all_codes[0]
            else:
                return self.resolve_ambiguity(all_codes)
        else:
            return self.resolve_ambiguity(family_codes)

    def code2parent(self, code: str, *args, **kwargs):
        parent = None
        try:
            parent = self._language_data[code].get("Parent")
        except KeyError:
            try:
                parent = self._family_data[code].get("Parent family")
            except KeyError:
                pass
        if parent:
            try:
                return self.name2code(parent, *args, **kwargs)
            except KeyError:
                # for parent entries "... family"
                return None

    def get_normalization_data(self):
        return {
            lang: v["normalization"]
            for lang, v in self._language_data.items()
            if "normalization" in v
        }

    def normalize(self, term: str, lang: str = None):
        if lang:
            if lang not in self:
                self.unknown_codes[lang] += 1
            else:
                try:
                    # default to lang if no parent
                    lang_or_parent = self.code2parent(lang) or lang
                    normalization = self.normalizations.get(lang_or_parent)
                    if normalization:
                        term = term.translate(normalization.translation_table)
                        for from_, to in normalization.complex_replacements:
                            term = re.sub(from_, to, term)
                        for d in normalization.complex_deletions:
                            term = re.sub(d, "", term)
                        if normalization.rm_diacritics_table:
                            term = unicodedata.normalize("NFD", term)
                            term = term.translate(normalization.rm_diacritics_table)
                            term = unicodedata.normalize("NFC", term)
                    return term
                except KeyError:
                    # unknown language id - no normalization possible
                    pass
        return term

    def is_family(self, code: str) -> bool:
        return code in self._family_data

    def get_family(self, code: str) -> str:
        if self.is_family(code):
            raise ValueError("Is a family.")
        return self._language_data[code].get("Family")


def load_phylogenetic_tree() -> nx.DiGraph:
    return nx.read_gpickle(
        io.BytesIO(importlib.resources.read_binary("etymmap.data", "langtree.gpickle"))
    )

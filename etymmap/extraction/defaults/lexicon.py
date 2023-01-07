import itertools
import logging
import pickle
from typing import Iterable, Mapping, List

import pandas as pd
from tqdm import tqdm

from etymmap.extraction.state import LexiconABC
from etymmap.graph import EntryLexeme, LexemeBase, NoEntryLexeme, SingleMeaningStub
from etymmap.specific import Specific
from etymmap.wiktionary import Wiktionary


class Lexicon(LexiconABC):
    _pickle = (
        "single_meanings",
        "n_single_meanings",
        "multi_meanings",
        "n_multi_meanings",
        "no_entries",
        "n_no_entries",
    )

    def __init__(self):
        """
        A rapid lookup for multi-meaning data and index for both single-meaning and multi-meaning lexemes
        """
        self.logger = logging.getLogger("Lexicon")
        self.single_meanings = {}
        self.n_single_meanings = 0
        self.multi_meanings = {}
        self.n_multi_meanings = 0
        # term -> language -> NoEntryLexeme
        self.no_entries = {}
        self.n_no_entries = 0

    @classmethod
    def from_wiktionary(
        cls,
        wiktionary: Wiktionary,
        index: pd.DataFrame = None,
    ) -> "Lexicon":
        """
        :param wiktionary:
        :param index:
        :return:
        """
        return cls().add_from_wiktionary(wiktionary, index)

    def add_from_wiktionary(self, wiktionary, index: pd.DataFrame = None):
        if index is None:
            self.logger.info("Retrieving wiktionary index.")
            index = wiktionary.export_index()
        self.logger.info("Split index into single and multiple meanings.")
        has_multi_meanings = index.etym_count > 1
        single_meanings_dict = {}
        single_meanings = index[~has_multi_meanings].index
        self.n_single_meanings = len(single_meanings)
        for term, language in single_meanings:
            stub = SingleMeaningStub(term, language)
            try:
                single_meanings_dict[term].append(stub)
            except AttributeError:
                single_meanings_dict[term] = [single_meanings_dict[term], stub]
            except KeyError:
                single_meanings_dict[term] = stub
        del single_meanings
        multi_meanings_dict = {}
        multi_meanings = index[has_multi_meanings].index
        self.n_multi_meanings = len(multi_meanings)
        for term, language in multi_meanings:
            multi_meanings_dict.setdefault(term, {})[language] = []
        self.single_meanings = single_meanings_dict
        self.multi_meanings = multi_meanings_dict
        self.logger.info("Initializing multi-meaning entries.")
        for i, entry in enumerate(
            tqdm(
                wiktionary.entries(filter={"etym_count": {"$gt": 1}}),
                total=self.n_multi_meanings,
                unit=" entries",
            )
        ):
            self.add_from_entry(entry)
        return self

    def to_pickle(self, path):
        with open(path, "wb") as dest:
            for attr in self._pickle:
                pickle.dump(self.__getattribute__(attr), dest)

    @classmethod
    def read_pickle(cls, path) -> "Lexicon":
        inst = cls()
        with open(path, "rb") as src:
            for attr in cls._pickle:
                setattr(inst, attr, pickle.load(src))
        return inst

    def add_from_entry(self, entry: Mapping) -> List[LexemeBase]:
        term = entry["title"]
        language = entry["language"]
        etym_count = entry["etym_count"]
        if etym_count > 1:
            lexemes = Specific.entry_parser.make_lexemes(entry)
            try:
                self.multi_meanings[term][language] = lexemes
                return lexemes
            except KeyError:
                raise KeyError(f"{term} {language} not in index.")
        else:
            return self._get_stub(term, language)

    def add_no_entry(
        self, term: str, language: str, template_data: Mapping = None
    ) -> LexemeBase:
        lexeme = NoEntryLexeme.from_template_data(term, language, template_data)
        self.no_entries.setdefault(term, []).append(lexeme)
        return lexeme

    def get(self, term, language=None, sense_idx=None) -> List[LexemeBase]:
        try:
            return self._get_stub(term, language)
        except KeyError:
            try:
                return self._get_multi_meaning(term, language, sense_idx)
            except KeyError:
                try:
                    return self._get_no_entry(term, language)
                except KeyError:
                    return []

    def __iter__(self) -> Iterable[LexemeBase]:
        def _single_meaning_stubs():
            for l in self.single_meanings.values():
                if isinstance(l, SingleMeaningStub):
                    yield l
                else:
                    yield from l

        return itertools.chain(
            _single_meaning_stubs(),
            (
                lexeme
                for by_term in self.multi_meanings.values()
                for lexemes in by_term.values()
                for lexeme in lexemes
            ),
            (lexeme for by_term in self.no_entries.values() for lexeme in by_term),
        )

    def _get_stub(self, term: str, language: str = None) -> List[SingleMeaningStub]:
        # single meanings
        with_term = self.single_meanings[term]
        # assume stub
        try:
            if language:
                if with_term.language == language:
                    return [with_term]
                raise KeyError((term, language))
            return [with_term]
        except AttributeError:
            # todo binary search if too slow
            if language:
                for stub in with_term:
                    if stub.language == language:
                        return [stub]
                raise KeyError((term, language))
            return with_term

    def _get_multi_meaning(
        self, term: str, language: str = None, sense_idx=None
    ) -> List[EntryLexeme]:
        with_term = self.multi_meanings[term]
        if language:
            lexemes = with_term[language]
            if sense_idx is not None:
                try:
                    lexeme = lexemes[sense_idx]
                    if lexeme.sense_idx == sense_idx:
                        return [lexeme]
                except IndexError:
                    pass
                for lexeme in lexemes:
                    if lexeme.sense_idx == sense_idx:
                        return [lexeme]
                raise KeyError((term, language, sense_idx))
            return lexemes
        return [lexeme for lexemes in with_term.values() for lexeme in lexemes]

    def _get_no_entry(self, term, language=None) -> List[NoEntryLexeme]:
        with_term = self.no_entries[term]
        if language:
            for lexeme in with_term:
                if lexeme.language == language:
                    return [lexeme]
            raise KeyError((term, language))
        return with_term

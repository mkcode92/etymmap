import unittest
from typing import List

from etymmap.specific.languages import (
    LanguageMapperABC,
)
from etymmap.specific_en import LanguageMapper, CachedLanguageDataUpdater


class LanguageMapperTest(unittest.TestCase):
    def setUp(self):
        self.mapper: LanguageMapperABC = LanguageMapper(
            updater=CachedLanguageDataUpdater()
        )

    def test_existing_code_to_name(self):
        codes_to_names = [
            ("och-ear", "Early Old Chinese"),
            ("com", "Comanche"),
            ("mjr", "Malavedan"),
            ("bfl", "Banda-Ndélé"),
            ("gvn", "Kuku-Yalanji"),
            ("cba-cat", "Catío Chibcha"),
            ("ccs-pro", "Proto-Kartvelian"),
            ("and", "Ansus"),
            ("ii", "Sichuan Yi"),
            ("xkj", "Kajali"),
        ]
        for code, name in codes_to_names:
            self.assertEqual(self.mapper.code2name(code), name)

    def test_unknown_code_raises_error(self):
        for not_a_code in ["asdf", "sdgf", "  ", "", None]:
            with self.assertRaises(KeyError):
                self.mapper.code2name(not_a_code)

    def test_unambiguous_names_to_string(self):
        canonical_names = ["Aweer", "Mundabli", "Bolon", "Bamako Sign Language"]
        other_names = [
            "Āḏarī",
            "Tamabo",
            "Beauceron",
            "Tarau",
            "Kurnay",
            "Western Jacalteco",
        ]
        for name in [*canonical_names, *other_names]:
            self.assertIsInstance(self.mapper.name2code(name), str)

    def test_ambiguous_names_to_list_or_resolved(self):
        ambiguous_names = ["Macu", "Koro", "Rgyalrong", "rGyalrong"]
        for name in ambiguous_names:
            self.assertIsInstance(
                self.mapper.name2code(name, allow_ambiguity=True), List
            )
            self.assertIsInstance(
                self.mapper.name2code(name, allow_ambiguity=False), str
            )

    def test_normalize(self):
        for (term, lang), normalized in [
            (("calendārium", "la"), "calendarium"),  # rm long vowel bar
            (("hée", "aa"), "hee"),  # rm accent
            (("word#Etymology 2", "la"), "word#Etymology 2"),
        ]:
            self.assertEqual(self.mapper.normalize(term, lang), normalized)

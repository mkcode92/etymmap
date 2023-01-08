from unittest import TestCase

from etymmap.specific_en import configure
configure()
from etymmap.extraction import Entities


class TestEntites(TestCase):
    def setUp(self):
        self.entites = Entities()

    def test_entites_are_added(self):
        self.entites.identify("test1", {"name": "test1"})
        self.entites.identify("test2", {"name": "test2"})
        self.assertEqual(2, len(self.entites.entities))

    def test_merge_when_no_conflict(self):
        e1 = self.entites.identify(
            "test1", {"name": "test1", "born": 1888, "occ": "occ1", "nat": "Turkish"}
        )
        e2 = self.entites.identify(
            "test1",
            {
                "name": "test1",
                "born": 1888,
                "wplink": "wikipedia.org/test1",
                "occ": "occ2",
            },
        )
        self.assertIs(e1, e2)
        self.assertEqual(1, len(self.entites.entities))
        self.assertEqual(1888, e1.born)
        self.assertEqual("wikipedia.org/test1", e1.wplink)
        self.assertEqual("Turkish", e1.nat)
        self.assertEqual("occ1; occ2", e1.occ)

    def test_not_merged_on_conflict(self):
        e1 = self.entites.identify("test1", {"name": "test1", "born": 2001})
        e2 = self.entites.identify("test1", {"name": "test1", "born": 1888})
        self.assertIsNot(e1, e2)

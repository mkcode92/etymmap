import unittest

import wikitextparser as wtp

from etymmap.api import PlainTextMapperABC
from etymmap.specific import PlainTextMapper


class TestPlainTextMapper(unittest.TestCase):
    def setUp(self):
        self.mapper: PlainTextMapperABC = PlainTextMapper()

    def test_string(self):
        self.assertEqual(self.mapper("hello"), "hello")

    def test_argument(self):
        template = wtp.parse("{{temp|arg1|arg2|t=arg3}}").templates[0]
        for arg, argtext in zip(template.arguments, ["arg1", "arg2", "arg3"]):
            self.assertEqual(self.mapper(arg), argtext)

    def test_wikilink(self):
        links = wtp.parse("[[hello]] [[hello#Etymology 5]] [[hello|bye]]").wikilinks
        for link, linktext in zip(links, ["hello", "hello", "bye"]):
            self.assertEqual(self.mapper(link), linktext)

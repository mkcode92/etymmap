import unittest
import wikitextparser as wtp

from etymmap.graph import RelationType
from etymmap.extraction import rules


class TestChainConversion(unittest.TestCase):
    def test_template_separation(self):
        self.assertIsInstance(
            rules.to_sequence("hello {{m|en|world}}!")[1], wtp.Template
        )

    def test_link_separation(self):
        self.assertIsInstance(rules.to_sequence("[[hello]] world")[0], wtp.WikiLink)

    def test_markup_separation(self):
        self.assertListEqual(
            [
                "hello",
                ("I", "start"),
                "world",
                ("I", "end"),
                ", and",
                ("B", "start"),
                "bye",
                ("B", "end"),
            ],
            rules.to_sequence("hello ''world'', and '''bye'''"),
        )

    def test_nested(self):
        i, link, i2 = rules.to_sequence("''[[hello]]''")
        self.assertEqual(("I", "start"), i)
        self.assertIsInstance(link, wtp.WikiLink)
        self.assertEqual(("I", "end"), i2)


class TestAnnotators(unittest.TestCase):
    def test_language_annotator(self):
        rule = rules.language_annotator
        anno = rule(rules.to_sequence("German diminutive of ''Haus''"))
        self.assertListEqual(
            [
                (rule.name, "German"),
                "diminutive of",
                ("I", "start"),
                "Haus",
                ("I", "end"),
            ],
            anno,
        )

    def test_language_annotator_recognizes_links(self):
        rule = rules.language_annotator
        anno = rule(rules.to_sequence("From the [[English]] word for ''cat''"))
        self.assertListEqual(
            [
                "From the",
                (rule.name, "English"),
                "word for",
                ("I", "start"),
                "cat",
                ("I", "end"),
            ],
            anno,
        )

    def test_language_annotator_skips(self):
        rule = rules.LanguageAnnotator(skip=("German",))
        anno = rule(rules.to_sequence("German diminutive"))
        self.assertListEqual(["German diminutive"], anno)

    def test_maybe_annotator(self):
        rule = rules.uncertain_annotator

        anno = rule(rules.to_sequence("The latter maybe from word"))
        self.assertListEqual(["The latter", (rule.name, "maybe"), "from word"], anno)

        anno = rule(rules.to_sequence("Probably borrowed from something"))
        self.assertListEqual([(rule.name, "Probably"), "borrowed from something"], anno)

    def test_from_annotator(self):
        rule = rules.from_annotator
        anno = rule(rules.to_sequence("From word1, from word2, ultimately from word3."))
        self.assertListEqual(
            [
                (rule.name, "From"),
                "word1,",
                (rule.name, "from"),
                "word2, ultimately",
                (rule.name, "from"),
                "word3.",
            ],
            anno,
        )

    def test_plus_annotator(self):
        rule = rules.plus_annotator
        anno = rule(rules.to_sequence("From ''hello''+''World''"))
        self.assertListEqual(
            [
                "From",
                ("I", "start"),
                "hello",
                ("I", "end"),
                (rule.name, "+"),
                ("I", "start"),
                "World",
                ("I", "end"),
            ],
            anno,
        )

    def test_punct_annotator(self):
        rule = rules.punct_annotator
        anno = rule(
            rules.to_sequence("This is a sentence, with a lot!? of interpunctuation.")
        )
        self.assertListEqual(
            [
                "This is a sentence",
                (rule.name, ","),
                "with a lot",
                (rule.name, "!?"),
                "of interpunctuation",
                (rule.name, "."),
            ],
            anno,
        )

    def test_xyof_annotator(self):
        rule = rules.XYAnnotator()
        anno = rule(
            rules.to_sequence(
                "The latter is a feminine plural of ''swimmer'', itself duplication of ..."
            )
        )
        self.assertListEqual(
            [
                "The latter is a",
                (rule.name, "feminine plural"),
                ("I", "start"),
                "swimmer",
                ("I", "end"),
                ", itself",
                (rule.name, "duplication"),
                "...",
            ],
            anno,
        )

    def test_wikipedia_annotator(self):
        rule = rules.WikipediaLinkAnnotator()
        anno = rule(
            rules.to_sequence(
                "This is a {{w|Template Representation|Template|lang=de}} of a link and this"
                " the [[w:fr:Template]] or [[w:Template]] representation"
            )
        )
        self.assertListEqual(
            [
                "This is a",
                (rule.name, "Template Representation", "de"),
                "of a link and this the",
                (rule.name, "Template", "fr"),
                "or",
                (rule.name, "Template", "en"),
                "representation",
            ],
            anno,
        )

    def test_quote_annotator(self):
        rule = rules.QuotesAnnotator()
        anno = rule(
            rules.to_sequence(
                'This is "a quoted phrase" and this is ``another`` and "here it does not close'
            )
        )
        self.assertListEqual(
            [
                "This is",
                (rule.name, "start"),
                "a quoted phrase",
                (rule.name, "end"),
                "and this is",
                (rule.name, "start"),
                "another",
                (rule.name, "end"),
                "and",
                (rule.name, "start"),
                "here it does not close",
            ],
            anno,
        )

    def test_maybe_mention(self):
        rule = rules.MaybeMentionAnnotator()
        anno = rule(rules.to_sequence("From this ''[[term]]'', cognate with ''words''"))
        self.assertListEqual(
            ["From this", (rule.name, "term"), ", cognate with", (rule.name, "words")],
            anno,
        )

    def test_maybe_gloss(self):
        rule = rules.SequenceRules(
            rules.literally_annotator,
            rules.QuotesAnnotator(),
            rules.brackets_annotator,
            rules.MaybeGlossAnnotator(),
        )
        anno = rule(rules.to_sequence('From [[hello]], meaning "to greet"'))
        self.assertEqual(
            (
                rules.MaybeGlossAnnotator.name,
                "to greet",
            ),
            anno[3],
        )
        anno = rule(rules.to_sequence('From [[hello]], meaning ("to greet")'))
        self.assertEqual(
            (
                rules.MaybeGlossAnnotator.name,
                "to greet",
            ),
            anno[3],
        )

    def test_mention(self):
        rule = rules.SequenceRules(
            rules.literally_annotator,
            rules.QuotesAnnotator(),
            rules.brackets_annotator,
            rules.LanguageAnnotator(),
            rules.plus_annotator,
            rules.punct_annotator,
            rules.MaybeMentionAnnotator(),
            rules.MaybeGlossAnnotator(),
            rules.ApplyTemplateNormalization(),
            rules.ApplyStringTokenization(),
            rules.MentionRule(),
        )
        anno = rule(
            rules.to_sequence(
                """Possibly from unattested ''[[kcić]]'', a corruption of ''[[chrzcić]]''
         ("to baptise"), as the sign ..."""
            )
        )
        self.assertListEqual(
            [
                "Possibly",
                "from",
                "unattested",
                ("Mention", {"term": "kcić"}),
                ("Punct", ","),
                "a",
                "corruption",
                "of",
                ("Mention", {"term": "chrzcić", "t": "to baptise"}),
                ("Punct", ","),
                "as",
                "the",
                "sign",
                ("Punct", "..."),
            ],
            anno,
        )

        anno = rule(
            rules.to_sequence(
                """'''[[teotl#Classical_Nahuatl|teōtl]]''' "god" + 
                                         '''[[piya#Classical_Nahuatl|piya]]''' "guard" + 
                                         '''[[-qui#Classical_Nahuatl|-qui]]'''"""
            )
        )
        self.assertEqual(
            [
                ("Mention", {"term": "teōtl", "t": "god"}),
                ("Plus", "+"),
                ("Mention", {"term": "piya", "t": "guard"}),
                ("Plus", "+"),
                ("Mention", {"term": "-qui"}),
            ],
            anno,
        )

        anno = rule(
            rules.to_sequence(
                """Compare West Frisian ''[[troch]]'', English ''[[through]]'',
        German ''[[durch]]''."""
            )
        )

        self.assertEqual(
            [
                "Compare",
                ("Mention", {"language": "West Frisian", "term": "troch"}),
                ("Punct", ","),
                ("Mention", {"term": "through", "language": "English"}),
                ("Punct", ","),
                ("Mention", {"term": "durch", "language": "German"}),
                ("Punct", "."),
            ],
            anno,
        )

    def test_compound_rule(self):
        rule = rules.SequenceRules(
            rules.literally_annotator,
            rules.QuotesAnnotator(),
            rules.brackets_annotator,
            rules.LanguageAnnotator(),
            rules.plus_annotator,
            rules.punct_annotator,
            rules.MaybeMentionAnnotator(),
            rules.MaybeGlossAnnotator(),
            rules.ApplyTemplateNormalization(),
            rules.ApplyStringTokenization(),
            rules.MentionRule(),
            rules.CompoundRule(),
        )
        anno = rule(
            rules.to_sequence(
                """Literally “to [[develop]] a [[talent]] with oneself”,
        from {{m|is|þroska||to [[develop]]}} + {{m|is|með||with}}
         + dative of {{m|is|sig||oneself}} + accusative of {{m|is|hæfileiki||talent}}."""
            )
        )
        compound_mentions = (
            {"language": "is", "term": "þroska", "alt": "", "t": "to develop"},
            {"language": "is", "term": "með", "alt": "", "t": "with"},
            {"language": "is", "term": "sig", "alt": "", "t": "oneself"},
            {"language": "is", "term": "hæfileiki", "alt": "", "t": "talent"},
        )
        self.assertEqual(5, len(anno))
        self.assertEqual(
            [
                ("Literally", "Literally"),
                ("Gloss?", "to develop a talent with oneself"),
                ("Punct", ","),
                "from",
            ],
            anno[:4],
        )
        self.assertEqual(anno[4].relation, {"type": RelationType.MORPHOLOGICAL})
        self.assertEqual(anno[4].link_target, compound_mentions)

import unittest
import wikitextparser as wtp

from etymmap.graph import RelationType
from etymmap.api import LinkNormalization
from etymmap.specific import Inject


class TestEtymologyTemplateHandler(unittest.TestCase):
    handler = Inject.template_handler

    def test_normalizations(self):
        def test(template, rel=None, src=None, tgt=None):
            template = wtp.parse(template).templates[0]
            n = self.handler.to_normalization(template)
            if rel:
                self.assertEqual(rel, n.relation)
            if src:
                self.assertEqual(src, n.link_source)
            if tgt:
                self.assertEqual(tgt, n.link_target)

        test(
            "{{derived|en|fr|bureaucrate}}",
            rel={"type": RelationType.DERIVATION},
            src={"language": "en"},
            tgt={"language": "fr", "term": "bureaucrate"},
        )

        test(
            "{{borrowed|en|de|Ablaut|gloss=sound gradation}}",
            rel={"type": RelationType.BORROWING},
            src={"language": "en"},
            tgt={"language": "de", "term": "Ablaut", "t": "sound gradation"},
        )

        test(
            "{{learned borrowing|en|la|aberrātiō|gloss=relief, diversion|notext=1}}",
            rel={"type": RelationType.LEARNED_BORROWING},
            src={"language": "en"},
            tgt={"language": "la", "term": "aberrātiō", "t": "relief, diversion"},
        )

        test(
            "{{desc|sq|thesar|bor=1}}",
            rel={"type": RelationType.BORROWING},
            tgt={"language": "sq", "term": "thesar"},
        )

        test(
            "{{desc|ro|tezaur|pclq=1|unc=1}}",
            rel={"type": RelationType.PARTIAL_CALQUE, "uncertain": True},
        )

        test(
            "{{back-formation|enm|waxen|t=to grow|id=to grow|nocap=1}}",
            rel={"type": RelationType.BACKFORM},
            tgt={"language": "enm", "term": "waxen", "t": "to grow", "id": "to grow"},
        )

        test(
            "{{onomatopoeic|en|title=onomatopoeic}}",
            rel={"type": RelationType.ONOM},
            tgt=LinkNormalization.NO_TARGET,
        )

        test(
            "{{unknown|la}}",
            rel={"type": RelationType.UNKNOWN},
            tgt=LinkNormalization.NO_TARGET,
        )

        test(
            "{{short for|ja|西本願寺|tr=Nishi Hongan-ji|nodot=1|sort=にし}}",
            rel={"type": RelationType.SHORTENING},
            tgt={"language": "ja", "term": "西本願寺", "tr": "Nishi Hongan-ji"},
        )

        test(
            "{{short for|vi|Thiên Can||[[celestial stem]]}}",
            rel={"type": RelationType.SHORTENING},
            tgt={
                "language": "vi",
                "term": "Thiên Can",
                "alt": "",
                "t": "celestial stem",
            },
        )

        test(
            "{{affix|en|a-|gloss1=towards|back|gloss2=back}}",
            rel={"type": RelationType.MORPHOLOGICAL},
            tgt=(
                {"language": "en", "term": "a-", "t": "towards"},
                {"language": "en", "term": "back", "t": "back"},
            ),
        )

        test(
            "{{named-after|es|nat=Genoese|occ=explorer|Christopher Columbus|wplink==|born=1451|died=1506}}",
            rel={"type": RelationType.EPONYM},
            tgt={
                "nat": "Genoese",
                "occ": "explorer",
                "name": "Christopher Columbus",
                "wplink": "=",
                "born": "1451",
                "died": "1506",
            },
        )

        test(
            "{{root|en|pie|*root1|*root2|id2=pie-root2}}",
            rel={"type": RelationType.INHERITANCE},
            tgt=(
                {"language": "pie", "term": "*root1"},
                {"language": "pie", "term": "*root2", "id": "pie-root2"},
            ),
        )

        test(
            "{{ar-root|س|ل|م}}",
            rel={"type": RelationType.INHERITANCE},
            tgt=({"language": "ar", "term": "س ل م"}),
        )

        test(
            "{{ja-r|羨ましい|うらやましい|t=enviable}}",
            rel={"type": RelationType.RELATED},
            tgt=(
                {"language": "ja", "term": "羨ましい", "ascii": "うらやましい", "t": "enviable"}
            ),
        )

        test(
            "{{ja-r|入手する||t=enviable|linkto=入手}}",
            rel={"type": RelationType.RELATED},
            tgt=(
                {
                    "language": "ja",
                    "term": "入手",
                    "ascii": "",
                    "alt": "入手する",
                    "t": "enviable",
                }
            ),
        )

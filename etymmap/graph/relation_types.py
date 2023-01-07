from enum import Enum
from typing import Union, Tuple, Any, Iterable, Dict, Mapping, Set


def _make_is_a_map(
    node: Union[Tuple, Any], ancestors: Iterable[Any] = (), _map: Dict = None
) -> Mapping[Any, Set[Any]]:
    """
    Collect transitive children for each node for faster lookup in type hierarchy

    :param node: the node in the recursion
    :param ancestors: the ancestors in the tree
    :param _map: a collector dictionary
    """
    _map = {} if _map is None else _map
    if isinstance(node, Tuple):
        node, children = node
        for child in children:
            _make_is_a_map(child, {node, *ancestors}, _map)
    _map[node] = {node, *ancestors}
    return _map


class RelationType(Enum):
    RELATED = "related"
    SIBLING = "sibling"
    COGNATE = "cognate"
    NONCOGNATE = "noncognate"
    DOUBLET = "doublet"
    ALTFORM = "alternative form"
    ORIGIN = "origin"
    HISTORICAL = "historical"
    INHERITANCE = "inheritance"
    DERIVATION = "derivation"
    ROOT = "root"
    BORROWING = "borrowing"
    LEARNED_BORROWING = "learned borrowing"
    SEMI_LEARNED_BORROWING = "semi-learned borrowing"
    ORTHOGRAPHIC_BORROWING = "orthographic borrowing"
    UNADAPTED_BORROWING = "unadapted borrowing"
    CALQUE = "calque"
    PARTIAL_CALQUE = "partial calque"
    SEMANTIC_LOAN = "semantic loan"
    PSM = "phono-semantic matching"
    MORPHOLOGICAL = "morphological"
    AFFIX = "affix"
    PREFIX = "prefix"
    INFIX = "infix"
    SUFFIX = "suffix"
    CONFIX = "confix"
    CIRCUMFIX = "circumfix"
    COMPOUND = "compound"
    UNIVERBATION = "univerbation"
    BLENDING = "blending"
    CLIPPING = "clipping"
    BACKFORM = "back-formation"
    ABBREV = "abbreviation"
    SHORTENING = "shortening"
    OTHER = "other"
    UNKNOWN = "unknown"
    EPONYM = "eponym"
    ONOM = "onomatopoeic"

    _ontology = (
        RELATED,
        [
            (SIBLING, [COGNATE, NONCOGNATE, DOUBLET, ALTFORM]),
            (
                ORIGIN,
                [
                    (HISTORICAL, [INHERITANCE, DERIVATION, ROOT]),
                    (
                        BORROWING,
                        [
                            LEARNED_BORROWING,
                            SEMI_LEARNED_BORROWING,
                            ORTHOGRAPHIC_BORROWING,
                            UNADAPTED_BORROWING,
                            CALQUE,
                            PARTIAL_CALQUE,
                            SEMANTIC_LOAN,
                            PSM,
                        ],
                    ),
                    (
                        MORPHOLOGICAL,
                        [
                            (AFFIX, [PREFIX, INFIX, SUFFIX, CONFIX, CIRCUMFIX]),
                            COMPOUND,
                            UNIVERBATION,
                            BLENDING,
                            CLIPPING,
                            BACKFORM,
                            ABBREV,
                            SHORTENING,
                        ],
                    ),
                    (OTHER, [UNKNOWN, EPONYM, ONOM]),
                ],
            ),
        ],
    )

    def is_a(self, other, _map=_make_is_a_map(_ontology)):
        return other.value in _map[self.value]

    @classmethod
    def get_ontology(cls):
        return cls._ontology.value

    @property
    def directed(self):
        return self.is_a(RelationType.ORIGIN)

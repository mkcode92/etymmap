import abc
import logging
from typing import Iterable, List, Union

import wikitextparser as wtp

from etymmap.extraction.state import NodeResolverABC, State
from .rules import SequenceRule, default_rules, to_sequence
from ..graph import (
    LexemeBase,
    Phantom,
    RelationType,
    DebugInfo,
    Relation,
    RelationAttributes,
)
from ..specific import Specific, LinkNormalization
from ..specific_en import consts, template_helper
from ..utils import tFlexStr, nonoverlapping, tMaybeParsed, get_items


class SectionExtractor(abc.ABC):
    name = ""

    def __init__(self, sections: tFlexStr):
        self.sections = sections
        self.logger = logging.getLogger(self.__class__.name)

    @abc.abstractmethod
    def extract(
        self, section: List[str], ctx_lexeme: LexemeBase, section_text: tMaybeParsed
    ) -> Iterable[RelationAttributes]:
        pass

    def handle_error(self, error):
        self.logger.debug(str(error))

    def relate_to_context_lexeme(
        self,
        target_obj: Union[wtp.Template, wtp.WikiLink, LinkNormalization],
        ctx_lexeme: LexemeBase,
        ctx_lexeme_source: bool = True,
        default_relation_type: RelationType = RelationType.RELATED,
        debug_info: DebugInfo = None,
    ) -> List[Relation]:
        if isinstance(target_obj, wtp.WikiLink):
            try:
                target = State.node_resolver.resolve_link(target_obj, ctx_lexeme)
            except NodeResolverABC.Underspecified as e:
                self.handle_error(e)
                return []
            if not target:
                return []
            if ctx_lexeme_source:
                source, target = ctx_lexeme, target
            else:
                source, target = target, ctx_lexeme
            return [Relation(source, target, RelationAttributes(default_relation_type))]
        else:
            if isinstance(target_obj, wtp.Template):
                try:
                    normalization = Specific.template_handler.to_normalization(
                        target_obj
                    )
                except NotImplementedError:
                    # we do not know how to handle the template
                    return []
            else:
                normalization = target_obj
            if isinstance(normalization.link_target, tuple):
                targets = tuple(
                    [
                        State.node_resolver.resolve_template(link_target, ctx_lexeme)
                        for link_target in normalization.link_target
                    ]
                )
            elif isinstance(normalization.link_target, dict):
                targets = [
                    State.node_resolver.resolve_template(
                        normalization.link_target, ctx_lexeme
                    )
                ]
            elif normalization.link_target is LinkNormalization.NO_TARGET:
                targets = [Phantom()]
            else:
                raise ValueError(f"Link target must not be None: {normalization}")
            # filter out nodes that could not be linked
            targets = [node for node in targets if node is not None]
            if targets:
                if ctx_lexeme_source:
                    sources = [ctx_lexeme]
                else:
                    sources = targets
                    targets = [ctx_lexeme]

                return [
                    Relation(
                        source,
                        target,
                        RelationAttributes(normalization.relation["type"]),
                    )
                    for source in sources
                    for target in targets
                ]
        return []


class BaselineExtractor(SectionExtractor):
    """
    Relate all template targets to the containing Lexeme
    """

    name = "Baseline"

    def extract(
        self, section: List[str], ctx_lexeme: LexemeBase, section_text: tMaybeParsed
    ) -> Iterable[RelationAttributes]:
        if isinstance(section_text, str):
            section_text = wtp.parse(section_text)
        ctx_lexeme_is_source = template_helper.context_lexeme_is_source(section)
        for template in nonoverlapping(section_text.templates)[0]:
            assert isinstance(template, wtp.Template)
            yield from self.relate_to_context_lexeme(
                template, ctx_lexeme, ctx_lexeme_is_source
            )


class LinkSectionExtractor(SectionExtractor):
    """
    Extracts relations from templates and wikilinks
    """

    def extract(
        self, section: List[str], ctx_lexeme: LexemeBase, section_text: tMaybeParsed
    ):
        if isinstance(section_text, str):
            section_text = wtp.parse(section_text)
        links_and_templates = nonoverlapping(
            [*section_text.templates, *section_text.wikilinks]
        )[0]
        ctx_lexeme_is_source = template_helper.context_lexeme_is_source(section)
        for link_or_template in links_and_templates:
            assert isinstance(link_or_template, (wtp.Template, wtp.WikiLink))
            try:
                yield from self.relate_to_context_lexeme(
                    link_or_template, ctx_lexeme, ctx_lexeme_is_source, debug_info=None
                )
            except NodeResolverABC.Underspecified as e:
                self.handle_error(e)


class RelatedTermsExtractor(LinkSectionExtractor):
    name = "RelatedTerms"

    def __init__(self):
        super().__init__(consts.RELATED_TERMS)


class DerivedTermsExtractor(LinkSectionExtractor):
    name = "DerivedTerms"

    def __init__(self):
        super().__init__(consts.DERIVED_TERMS)


class DescendantsSectionExtractor(SectionExtractor):
    name = "Descendants"

    def __init__(self, out_of_list_templates=True):
        """
        Descendants sections normally consist of a list of descendants templates, that specify the type of relation
        as a keyword parameter
        """
        super().__init__(consts.DESCENDANTS)
        self.out_of_list_templates = out_of_list_templates

    def extract(
        self, section: List[str], ctx_lexeme: LexemeBase, section_text: tMaybeParsed
    ):
        parsed = (
            wtp.parse(section_text) if isinstance(section_text, str) else section_text
        )
        lists = parsed.get_lists()

        def from_list(current_list, current_context_lexeme):
            sub_ctx = current_context_lexeme
            for i, item1 in enumerate(get_items(current_list, avoid_reparse=True)):
                templates = item1.templates
                if not templates:
                    sub_ctx = current_context_lexeme
                for template in templates:
                    relations = self.relate_to_context_lexeme(
                        template,
                        current_context_lexeme,
                        True,
                        debug_info=None,
                    )
                    if relations:
                        yield from relations
                        if len(relations) == 1:
                            sub_ctx = relations[0].tgt
                # for tree-like lists, set inner ctx
                for l2 in current_list.sublists(i):
                    yield from from_list(l2, sub_ctx)

        for list_ in lists:
            yield from from_list(list_, ctx_lexeme)

        if self.out_of_list_templates:
            for template_or_list in nonoverlapping(parsed.templates + lists):
                if isinstance(template_or_list, wtp.Template):
                    try:
                        yield from self.relate_to_context_lexeme(
                            template_or_list,
                            ctx_lexeme,
                            True,
                            debug_info=None,  # todo add debug info
                        )
                    except NodeResolverABC.Underspecified as e:
                        self.handle_error(e)


class EtymologySectionExtractor(SectionExtractor):
    name = "Etymology"

    def __init__(
        self,
        rules: SequenceRule = default_rules,
        chain_resolution: bool = True,
        only_first_sentence: bool = True,
        only_in_from_chain: bool = True,
    ):
        super().__init__(consts.ETYMOLOGY_SECTION)
        self.rules = rules
        self.template2relation = Specific.template_handler.templates_to_relation()
        self.chain_resolution = chain_resolution
        self.chain_resolution_counter = [0, 0]
        self.only_first_sentence = only_first_sentence
        self.only_in_from_chain = only_in_from_chain

    def extract(
        self, section: List[str], ctx_lexeme: LexemeBase, section_text: tMaybeParsed
    ) -> Iterable[RelationAttributes]:
        """
        Extract from the etymology sections.

        1. Convert into chains
        2. Apply rules
        3. with chain resolution, consequent ORIGIN relations are treated as
        etymological chains, and the relation target is the previous
        relation source
        4. Otherwise, the containing lexeme is chosen as target

        :param section:
        :param ctx_lexeme:
        :param section_text:
        :return:
        """
        if isinstance(section_text, str):
            section_text = wtp.parse(section_text)

        sequence = to_sequence(section_text)

        # if this turn out to be too expensive,
        # we should maybe only apply if there are
        # no specific_en templates in the section
        chain = self.rules(sequence)

        chain_resolution = self.chain_resolution
        last_origin_source = None
        # either we are currently right after a from or 'from's are ignored
        from_chain_check = not self.only_in_from_chain
        first_sentence_check = True
        section_relations = []

        for e in chain:
            if isinstance(e, LinkNormalization):
                if (
                    chain_resolution
                    and last_origin_source
                    and from_chain_check
                    and first_sentence_check
                ):
                    relations = self.relate_to_context_lexeme(
                        e, last_origin_source, False, debug_info=None
                    )
                    self.logger.debug(
                        f"Applying transitivity unpacking: {relations} instead of linking to {ctx_lexeme}."
                    )
                    self.chain_resolution_counter[0] += len(relations)
                else:
                    relations = self.relate_to_context_lexeme(
                        e, ctx_lexeme, False, debug_info=None
                    )
                    self.chain_resolution_counter[1] += len(relations)

                # it is unclear how to link if the previous source was a compound
                if chain_resolution and len(relations) == 1:
                    last_relation = relations[0]
                    last_type = last_relation.attrs.type
                    if (
                        last_type.is_a(RelationType.ORIGIN)
                        and not last_type.is_a(RelationType.ROOT)
                        and isinstance(last_relation.src, LexemeBase)
                    ):
                        last_origin_source = last_relation.src
                        from_chain_check = not self.only_in_from_chain

                section_relations.extend(relations)

            # EOS
            elif e == ("Punct", "."):
                last_origin_source = None
                first_sentence_check = not self.only_first_sentence
                from_chain_check = not self.only_in_from_chain

            elif not from_chain_check and isinstance(e, tuple) and e[0] == "From":
                from_chain_check = True

        yield from section_relations

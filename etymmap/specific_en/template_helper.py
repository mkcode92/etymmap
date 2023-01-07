import logging
import re
from collections import defaultdict
from typing import Mapping, List, Set, Iterable, Optional, MutableMapping, Tuple

import wikitextparser as wtp

from etymmap.graph import RelationType
from etymmap.specific import (
    Specific,
    LinkSemantics,
    LinkNormalization,
    TemplateParameter,
    TemplateHandler,
)
from etymmap.utils import Equivalent, tFlexStr
from . import consts

logger = logging.getLogger("Templates")


class TemplatePreprocessor:
    def __init__(
        self,
        params_keep: Iterable[str],
        renaming: Mapping[str, str] = None,
        indexed_keys: bool = False,
        link_args=("term",),
    ):
        """
        Template parameter normalization, filtering and string mapping

        :param: params_keep: the relevant parameter names
        :param: renaming: a mapping of parameter name alias to parameter name
        :param: indexed_keys: if false, indexed parameter names are combined into a single string
        :param: link_args: names of arguments, whose values are needed vor linking
        """
        self.params_keep = set(params_keep)
        self.renaming = renaming or {}
        self.indexed_keys = indexed_keys
        # params regex is necessary to also find indexed parameters
        self.params_regex = self._make_params_regex()
        self.link_args = link_args

    def __call__(
        self,
        template: wtp.Template,
        argmap: Mapping = None,
        recursive=True,
    ) -> List[TemplateParameter]:
        template_args = []
        indexed_args = defaultdict(list)
        for a in template.arguments:
            name = a.name.strip()
            if argmap:
                name = argmap.get(name, name)
            name = self.renaming.get(name, name)
            if name in self.link_args:
                value = a.value
            else:
                value = Specific.plain_text(a, recursive=recursive).strip()
            if name in self.params_keep or a.positional:
                template_args.append((name, value))
            else:
                m = self.params_regex.match(name)
                if m:
                    name, index = m.group(1), int(m.group(2))
                    name = self.renaming.get(name, name)
                    if self.indexed_keys:
                        template_args.append(((name, index), value))
                    else:
                        # maybe collect not indexed first element
                        list_ = indexed_args[name]
                        if not list_:
                            for n, v in template_args[::-1]:
                                if n == name:
                                    list_.append(v)
                                    break
                        list_.append(value)
        if indexed_args:
            # make sure all values are strings
            template_args.extend((k, ";".join(v)) for k, v in indexed_args.items())
        return template_args

    def _make_params_regex(self):
        return re.compile(
            f"({'|'.join([*self.params_keep, *self.renaming])})" + r"(\d+)"
        )


class AllTargetParameters(LinkSemantics):
    """
    All Parameters describe the single target of the link
    """

    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        return LinkNormalization({"type": default_relation}, {}, dict(template_args))


class DescendantsSemantics(LinkSemantics):
    """
    Relation type is encoded as boolean parameter
    """

    relation_flags = {
        "bor": RelationType.BORROWING,
        "lbor": RelationType.LEARNED_BORROWING,
        "slb": RelationType.SEMI_LEARNED_BORROWING,
        "cal": RelationType.CALQUE,
        "pclq": RelationType.PARTIAL_CALQUE,
        "sml": RelationType.SEMANTIC_LOAN,
        "der": RelationType.DERIVATION,
    }

    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        rel = {}
        tgt = {}
        type_ = default_relation
        for a, v in template_args:
            if a == "unc":
                rel["uncertain"] = True
            else:
                try:
                    type_ = self.relation_flags[a]
                except KeyError:
                    tgt[a] = v
        rel["type"] = type_
        return LinkNormalization(rel, {}, tgt)


class TargetWithSourceLang(LinkSemantics):
    """
    All params but the first lang=xy describe the link target

    roughly equivalent: etymology.templates.parse_2_lang_args
    """

    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        rel = {"type": default_relation}
        src = {}
        tgt = {}
        source_lang_unset = True
        for name, value in template_args:
            if source_lang_unset and name == "language":
                src[name] = value
                source_lang_unset = False
            else:
                tgt[name] = value
        return LinkNormalization(rel, src, tgt)


class MultipleTargets(LinkSemantics):
    """
    Params are indexed and refer to multiple targets

    includes equivalences to etymolgy.templates.misc_values
    """

    def __init__(self, with_target_language=False):
        self.with_target_language = with_target_language

    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        # multi relations
        lkey, lang = template_args[0]
        if not lkey == "language":
            logger.warning(
                f"{self.__class__.__name__}: First parameter should be lang, but is {lkey}"
            )
        src = {"language": lang}
        tgts = defaultdict(dict)
        offset = 2 if self.with_target_language else 1
        for a, v in template_args[offset:]:
            try:
                # positional args are terms
                tgts[int(a) - offset - 1]["term"] = v
            except (TypeError, ValueError):
                if isinstance(a, str):
                    param, idx = a, 1
                else:
                    param, idx = a
                tgts[idx - 1][param] = v
        tgts = tuple(v for _, v in sorted(tgts.items()))
        tgt_lang = src["language"]
        if self.with_target_language:
            try:
                lkey, tgt_lang = template_args[1]
                if lkey != "language":
                    logger.warning(
                        f"{self.__class__.__name__}: First parameter should be lang, but is {lkey}"
                    )
            except IndexError:
                logger.warning(
                    f"{self.__class__.__name__}: Missing target language parameter {template_args}"
                )
        for tgt in tgts:
            if "language" not in tgt:
                tgt["language"] = tgt_lang
        return LinkNormalization({"type": default_relation}, src, tgts)


class UnknownTarget(LinkSemantics):
    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        return LinkNormalization(
            {"type": default_relation},
            dict(template_args[:1]),
            LinkNormalization.NO_TARGET,
        )


class PlainMultiLinks(LinkSemantics):
    def __call__(
        self, default_relation: RelationType, template_args: List[TemplateParameter]
    ) -> LinkNormalization:
        lang = template_args[0][1]
        skip_first = True
        if lang not in Specific.language_mapper:
            lang = next((a for k, a in template_args if k == "language"), None)
            skip_first = False
            if not lang:
                logger.warning(f"Missing language identifier {template_args}")
        return LinkNormalization(
            {"type": default_relation},
            {"language": lang},
            tuple(
                {"term": term, "language": lang}
                for k, term in template_args[1 if skip_first else 0 :]
                if k != "language"
            ),
        )


default_params = {
    "language",  # language
    "term",  # related term
    "alt",  # alternative form
    "t",  # translation/gloss
    "tr",  # transliteration
    "pos",  # pos
    "id",  # sense_id
    "ts",  # transcription
    "lit",  # literal translation
    "g",  # gender/number
    "q",  # qualifier (may correspond to labels)
}
default_renaming = {
    "gloss": "t",
    "occupation": "occ",
    "nationality": "nat",
    "lang": "language",
    "qual": "q",
}

default_preprocessor = TemplatePreprocessor(
    params_keep=default_params, renaming=default_renaming, indexed_keys=False
)

multi_term_preprocessor = TemplatePreprocessor(
    params_keep=default_params, renaming=default_renaming, indexed_keys=True
)


class SpecificTemplateHandler(TemplateHandler):
    """
    A specific_en template handler, defining alias names & semantics
    """

    def __init__(
        self,
        name: str,
        *other_names: tFlexStr,
        default_relation: RelationType = None,
        positional_args: Iterable[str] = (),
        link_semantics: Optional[LinkSemantics] = TargetWithSourceLang(),
        preprocessor: Optional[TemplatePreprocessor] = default_preprocessor,
        template2plaintext=None,
        relation_in_text: tFlexStr = "",
        lang_in_text=False,
        multiple_joiner=" and ",
    ):
        """
        Defines the handling for equivalent templates (mostly a template and it's alias)

        :param name: the representative name of the template group
        :param other_names: names of equivalent templates or alias
        :param default_relation: the relation this template maps onto (may be overridden in normalization)
        :param positional_args: the parameter names for positional arguments
        :param link_semantics: associates template parameters with relation, src, tgt objects
        :param preprocessor: normalization, filtering and string mapping of template parameters
        :param template2plaintext: ad-hoc method to translate template to a string (mind nested wikitext elements)
        :param relation_in_text: display the name in the plaintext
        :param lang_in_text: display the language name in the plaintext
        :param multiple_joiner: how to join the plaintext if the template refers to multiple elements
        """
        # match params
        self._names = Equivalent()
        self._names.declare(name, *other_names)
        # the default associated relation
        if default_relation:
            self.default_relation = default_relation
        else:
            try:
                self.default_relation = RelationType(name)
            except ValueError:
                self.default_relation = None

        # normalization params
        self.argmap = {str(i + 1): a for i, a in enumerate(positional_args)}
        self.link_semantics = link_semantics
        self.preprocessor = preprocessor

        # to_text params
        self.template2plaintext = template2plaintext
        self.relation_in_text = relation_in_text
        self.lang_in_text = lang_in_text
        self.multiple_joiner = multiple_joiner

    def get_names(self):
        return {r: self._names.group(r) for r in self._names}

    def to_normalization(
        self, template: wtp.Template, recursive=True
    ) -> LinkNormalization:
        if not (self.preprocessor and self.link_semantics):
            raise NotImplementedError(template.name)
        params = self.preprocessor(template, self.argmap, recursive=recursive)
        return self.link_semantics(self.default_relation, params)

    def to_text(self, template: wtp.Template, recursive=True) -> str:
        if self.template2plaintext:
            return self.template2plaintext(template).strip()

        tgt = self.to_normalization(template).link_target
        if isinstance(tgt, Tuple):
            tgt = self.multiple_joiner.join(
                [self.obj2text(t, template.name.strip()) for t in tgt]
            )
        else:
            tgt = self.obj2text(tgt, template.name.strip())
        return tgt.strip()

    def obj2text(
        self,
        obj: MutableMapping,
        template_name: str,
        _annomap=(
            ("pos", "{}".format),
            ("t", '<i> "{}" </i>'.format),
            ("tr", "{}".format),
            ("ts", "{}".format),
            ("lit", 'literally "{}"'.format),
            (
                "g",
                lambda g: "gender/number {}".format(
                    g if isinstance(g, str) else " or ".join(g)
                ),
            ),
            ("q", "({})".format),
        ),
    ):
        # roughly Module:links.format_link_annotations
        ret = []

        if self.relation_in_text:
            if isinstance(self.relation_in_text, str):
                ret.append(self.relation_in_text)
            else:
                ret.append(
                    self.relation_in_text.match(template_name).string.replace("-", " ")
                )

        if self.lang_in_text:
            lang = obj.get("language")
            try:
                ret.append(Specific.language_mapper.code2name(lang))
            except KeyError:
                pass

        term = obj.get("alt", obj.get("term", ""))
        if term and term != "-":
            ret.append(term)

        annotations = []
        for k, f in _annomap:
            v = obj.get(k)
            if v:
                annotations.append(f(v))
        if annotations:
            ret.append(f"({', '.join(annotations)})")
        return " ".join(ret)

    def get_relation_mapping(self) -> Mapping[str, Set[str]]:
        return {self.default_relation: set(self._names)}

    def templates_to_relation(self, alias=True) -> Mapping[str, RelationType]:
        if self.default_relation is None:
            return {}
        return {
            name: self.default_relation
            for name in (self._names.map if alias else self._names)
        }


class CompositeTemplateHandler(TemplateHandler):
    def __init__(self, *specific_template_handlers: SpecificTemplateHandler):
        self._names = Equivalent()
        self._specific_handlers = {}
        for s in specific_template_handlers:
            representative, other_names = next(iter(s.get_names().items()))
            self._names.declare(representative, *(other_names - {representative}))
            self._specific_handlers[representative] = s

    def get_specific_handler(self, name: str) -> SpecificTemplateHandler:
        try:
            return self._specific_handlers[name]
        except KeyError:
            try:
                return self._specific_handlers[self._names[name]]
            except KeyError:
                raise NotImplementedError

    def to_text(self, template: wtp.Template, recursive=True) -> str:
        try:
            return self.get_specific_handler(template.name.strip()).to_text(
                template, recursive=True
            )
        except NotImplementedError:
            return template.string

    def to_normalization(
        self, template: wtp.Template, recursive=True
    ) -> LinkNormalization:
        return self.get_specific_handler(template.name.strip()).to_normalization(
            template, recursive
        )

    def templates_to_relation(self, alias=True) -> Mapping[str, RelationType]:
        return {
            k: v
            for specific_handler in self._specific_handlers.values()
            for k, v in specific_handler.templates_to_relation().items()
        }

    def get_names(self):
        return {
            r: names
            for s in self._specific_handlers.values()
            for r, names in s.get_names().items()
        }

    def get_relation_mapping(self) -> Mapping[RelationType, Set[str]]:
        ret = defaultdict(set)
        for s in self._specific_handlers.values():
            for relation, template_names in s.get_relation_mapping().items():
                ret[relation] |= template_names
        return dict(ret)


def context_lexeme_is_source(section: List[str]) -> bool:
    return not consts.ETYMOLOGY_SECTION.match(section[-1])

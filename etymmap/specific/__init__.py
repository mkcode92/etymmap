from .languages import LanguageDataUpdaterABC, LanguageMapperABC
from .parsing import EntryParserABC
from .plain_text import PlainTextMapperABC
from .templates import (
    LinkNormalization,
    LinkSemantics,
    TemplateHandler,
    TemplateParameter,
)


# for injection of singletons
class Specific:
    __slots__ = ("language_mapper", "entry_parser", "template_handler", "plain_text")
    language_mapper: LanguageMapperABC
    entry_parser: EntryParserABC
    template_handler: TemplateHandler
    plain_text: PlainTextMapperABC

    @classmethod
    def configure(
        cls,
        language_mapper: LanguageMapperABC,
        entry_parser: EntryParserABC,
        template_handler: TemplateHandler,
        plain_text: PlainTextMapperABC,
    ):
        cls.language_mapper = language_mapper
        cls.entry_parser = entry_parser
        cls.template_handler = template_handler
        cls.plain_text = plain_text

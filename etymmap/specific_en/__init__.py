from .languages import LanguageMapper, CachedLanguageDataUpdater
from .parsing import EntryParser
from .plain_text import PlainTextMapper
from .templates import EtymologyTemplateHandler


def configure():
    from etymmap.specific import Specific

    Specific.configure(
        LanguageMapper(CachedLanguageDataUpdater()),
        EntryParser(),
        EtymologyTemplateHandler(),
        PlainTextMapper(),
    )

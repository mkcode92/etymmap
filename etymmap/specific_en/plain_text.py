from typing import Union, Any

import wikitextparser as wtp

from etymmap.specific import Specific, PlainTextMapperABC
from etymmap.utils import (
    make_parsed_subsection,
    analyze_link_target,
    nonoverlapping,
)


class PlainTextMapper(PlainTextMapperABC):
    def __init__(self):
        self.typemap = {
            str: self.process_str,
            wtp.Argument: self.process_argument,
            wtp.Template: self.process_template,
            wtp.WikiLink: self.process_wikilink,
            wtp.ExternalLink: self.process_external_link,
            wtp.Italic: self.process_italics,
            wtp.Bold: self.process_bold,
            wtp.Tag: self.process_tag,
            wtp.Section: self.process_recursive,
            wtp.WikiText: self.process_recursive,
            wtp.Comment: self.process_comment,
        }

    def __call__(
        self, elem: Union[str, wtp.WikiText], recursive: bool = True, join=" "
    ) -> str:
        return self.typemap.get(type(elem), self.process_fallback)(elem, recursive)

    def process_str(self, elem: str, recursive: bool) -> str:
        return elem

    def process_argument(self, elem: wtp.Argument, recursive: bool) -> str:
        """
        Get value as plain text
        """
        if recursive:
            if elem.positional:
                return self(make_parsed_subsection(elem, 1))  # strip |
            else:
                return self(
                    make_parsed_subsection(elem, len(elem.name) + 2)
                )  # strip |name=
        return elem.value

    def process_template(self, elem: wtp.Template, recursive: bool) -> str:
        return Specific.template_handler.to_text(elem, recursive=recursive)

    def process_wikilink(self, elem: wtp.WikiLink, recursive: bool) -> str:
        title, fragment, special = analyze_link_target(elem.target)
        if special and special not in ("wikipedia", "Reconstruction"):
            return ""
        if recursive:
            if elem.templates:
                # this is not efficient, but very rare
                return self(wtp.parse(title))
        return title

    def process_external_link(self, elem: wtp.ExternalLink, recursive: bool) -> str:
        return elem.text or elem.url

    def process_italics(self, elem: wtp.Italic, recursive: bool) -> str:
        if recursive:
            string = self(make_parsed_subsection(elem, 2, -2))
        else:
            string = elem.text
        return f"<i>{string}</i>"

    def process_bold(self, elem: wtp.Bold, recursive) -> str:
        if recursive:
            string = self(make_parsed_subsection(elem, 3, -3))
        else:
            string = elem.text
        return f"<b>{string}</b>"

    def process_recursive(self, elem: wtp.WikiText, recursive: bool) -> str:
        elements, is_recursive = nonoverlapping(
            [
                *elem.templates,
                *elem.wikilinks,
                *elem.external_links,
                *elem.get_bolds_and_italics(recursive=False),
                *elem.comments,
                *elem.get_tags(),
            ]
        )
        if not elements:
            return elem.string
        text = elem.string
        ref_start, ref_end = elem.span
        ret = []
        s = 0
        for e, r in zip(elements, is_recursive):
            start, end = e.span
            start -= ref_start
            end -= ref_start
            ret.append(text[s:start])
            ret.append(self(e, recursive=r))
            s = end
        ret.append(text[s:])
        return "".join(ret)

    def process_tag(self, elem: wtp.Tag, recursive: bool) -> str:
        if elem.name in {"sup", "sub"}:
            return elem.contents
        else:
            return ""

    def process_comment(self, elem: wtp.Comment, recursive: bool) -> str:
        return ""

    def process_fallback(self, elem: Any, recursive: bool) -> str:
        return str(elem)

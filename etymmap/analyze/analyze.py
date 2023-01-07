import csv
import logging
from collections import Counter
from pathlib import Path
from typing import List

import pandas as pd
import wikitextparser as wtp

from etymmap.specific import Specific
from etymmap.utils import SectionText
from etymmap.wiktionary import DumpProcessor, raw2json


def collect_path(raw_page_chunk):
    def _collect_path(elem):
        ret = []
        if isinstance(elem, dict):
            for k, v in elem.items():
                ret.append(k)
                ret.extend(f"{k}.{c}" for c in _collect_path(v))
        elif isinstance(elem, list):
            for i, v in enumerate(elem):
                ret.append(f"[*]")
                ret.extend(f"[*].{c}" for c in _collect_path(v))
        return ret

    paths = set()
    for raw_page in raw_page_chunk:
        json_page = raw2json(raw_page)
        for path in _collect_path(json_page):
            paths.add(path)
    return paths


def inspect_json_paths(
    dump_processor: DumpProcessor, head=10**6, chunksize_bytes=10**7, **kwargs
):
    paths = set()
    for chunk_paths in dump_processor.apply(
        collect_path,
        head=head,
        chunksize_bytes=chunksize_bytes,
        progress={"unit": " pages", "total": head},
        **kwargs,
    ):
        paths |= chunk_paths
    return paths


columns = {
    "pages": ["id", "title", "namespace"],
    "revisions": ["page_id", "id", "timestamp", "contributor", "minor"],
    "contributors": ["id", "username", "ip"],
    "entries": [
        "revision_id",
        "language",
        "size",
        "n_sections",
        "has_etymology",
        "templates",
    ],
}


class StatisticsReader:
    def __init__(self, path="."):
        self.path = Path(path)

    def pages(self, **kwargs):
        return self._read(
            "pages", {"id": "uint32", "title": str, "namespace": "int16"}, **kwargs
        )

    def revisions(self, **kwargs):
        return self._read(
            "revisions",
            {"page_id": "uint32", "id": "uint32", "contributor": str, "minor": bool},
            parse_dates=["timestamp"],
            **kwargs,
        )

    def contributors(self, **kwargs):
        return self._read("contributors", {}, **kwargs)

    def entries(self, **kwargs):
        return self._read(
            "entries",
            {
                "revision_id": "uint32",
                "language": "str",
                "size": "uint16",
                "n_sections": "uint16",
                "has_etymology": bool,
                "templates": str,
            },
            keep_default_na=False,
            **kwargs,
        )

    def _read(self, name: str, dtype: dict, **kwargs):
        if "usecols" in kwargs:
            usecols = kwargs["usecols"]
            dtype = {k: v for k, v in dtype.items() if k in usecols}
            kwargs["parse_dates"] = [
                c for c in kwargs.get("parse_dates", []) if c in usecols
            ]
        return pd.read_csv(self.path / (name + ".csv"), header=0, dtype=dtype, **kwargs)


class StatisticsWriter:
    def __init__(
        self,
        skip_minor_revisions=True,
        include_last_revision=True,
        parse_namespaces=(0, 118),
    ):
        self.skip_minor_revisions = skip_minor_revisions
        self.include_last_revision = include_last_revision
        self.logger = logging.getLogger("statistics")
        self.parse_namespaces = set(parse_namespaces)

    def write_stats(
        self, dump: DumpProcessor, out=".", chunksize_bytes=10**7, **kwargs
    ):
        out = Path(out)
        files = []
        writers = {}
        for name, column in columns.items():
            file = open(out / f"{name}.csv", "w")
            writer = csv.writer(file, delimiter=",", quoting=csv.QUOTE_ALL)
            writer.writerow(column)
            files.append(file)
            writers[name] = writer
        contributors = set()
        try:
            for collector in dump.apply(
                self.collect_chunk_stats,
                chunksize_bytes=chunksize_bytes,
                **kwargs,
            ):
                for k, stats in collector.items():
                    if k == "contributors":
                        contributors.update(stats)
                    else:
                        writers[k].writerows(stats)
                        self.logger.debug(f"{k}:{len(stats)} rows.")
            writers["contributors"].writerows(contributors)
        finally:
            for file in files:
                file.close()

    def new_collector(self):
        return {k: [] for k in columns}

    def collect_chunk_stats(self, raw_pages: List[bytes]):
        collector = self.new_collector()
        for raw_page in raw_pages:
            self.collect_page_stats(raw_page, collector)
        return collector

    def collect_page_stats(self, raw_page, collector=None) -> dict:
        """
        Extract the statistics for a page for the levels page, revisions or sections.
        Revision and section statistics require revision text parsing.

        :param raw_page: the page obtained by a DumpProcessor
        :param collector: a dictionary to collect the records per table
        :return: the collector filled with lists of records (tuples) per table
        """
        collector = collector or self.new_collector()
        json_page = raw2json(raw_page)
        if not json_page.get("partial"):
            collector["pages"].append(
                (json_page["id"], json_page["title"], json_page["ns"])
            )
        # revisions can be empty if the page was split
        revisions = json_page.get("revision", [])
        for i, revision in enumerate(revisions):
            revision_id = revision["id"]
            contributor = revision["contributor"]
            if isinstance(contributor, dict):
                contributor = tuple(
                    contributor.get(k) for k in ["id", "username", "ip"]
                )
                contributor_id = contributor[0] or contributor[2] or "-"
                collector["contributors"].append(contributor)
            else:
                self.logger.warning(
                    f"Cannot identify contributor ({json_page['id']}.{revision['id']}): {contributor}"
                )
                contributor_id = "-"
            collector["revisions"].append(
                (
                    json_page["id"],
                    revision_id,
                    revision["timestamp"],
                    contributor_id,
                    revision.get("minor", False),
                )
            )

            if revision.get("minor"):
                # ignore minors, but maybe keep most recent revision
                if self.skip_minor_revisions:
                    if not (self.include_last_revision and i == len(revisions) - 1):
                        continue

            if json_page["ns"] not in self.parse_namespaces:
                continue

            parsed = wtp.parse(revision["text"])
            text_sections = SectionText(
                parsed, Specific.entry_parser.parse_section(parsed)
            )

            language = old_language_name = None
            has_etymology = False
            size = n_sections = 0
            template_counts = Counter()

            for section, text in text_sections.iteritems():
                language_name = section[0]
                if language_name != old_language_name:
                    if language:
                        collector["entries"].append(
                            (
                                revision_id,
                                language,
                                size,
                                n_sections,
                                has_etymology,
                                "|".join(
                                    f"{t}={c}" for t, c in template_counts.items()
                                ),
                            )
                        )
                        has_etymology = False
                        size = n_sections = 0
                        template_counts.clear()
                        old_language_name = language_name
                    try:
                        language = Specific.language_mapper.name2code(language_name)
                    except (KeyError, ValueError):
                        language = "?" + language_name
                size += len(text)
                n_sections += 1
                if section[-1].startswith("Etym"):
                    has_etymology = True
                    template_counts.update([t.name for t in text.templates])

            if language:
                collector["entries"].append(
                    (
                        revision_id,
                        language,
                        size,
                        n_sections,
                        has_etymology,
                        "|".join(f"{t}={c}" for t, c in template_counts.items()),
                    )
                )

        return collector

import csv
import itertools
import logging
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Tuple, Mapping, Union

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegressionCV
from sklearn.metrics import precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler

from etymmap.extraction import BaselineExtractor, EtymologyExtractor, init_and_configure
from etymmap.extraction.state import GlossMergeListener, GlossMatcherABC
from etymmap.extraction.state.gloss_matching import Levenshtein
from etymmap.graph import LexemeBase, SingleMeaningStub, EntryLexeme, Node
from etymmap.specific_en.consts import ETYMOLOGY_SECTION
from etymmap.wiktionary import Wiktionary

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("MongoEntryStore").setLevel(logging.INFO)
logging.getLogger("matplotlib").setLevel(logging.INFO)


class IdMergeListener(GlossMergeListener):
    """
    A merge listener that tracks only merging by ids (etymid, senseid)
    """

    def __init__(self):
        self.items = defaultdict(set)
        self.auto_items_etym = defaultdict(set)
        self.auto_items_sense = defaultdict(set)

    def __call__(
        self, event: "GlossMergeListener.Event", template_data: Mapping, node: Node
    ):

        if isinstance(node, SingleMeaningStub):
            return

        # only listen for id merge
        if event > 4:
            return

        # single meaning stub and entity are not possible here
        node: Union[LexemeBase, EntryLexeme] = node
        with_gloss = template_data and template_data.get("t")
        _e = self.Event
        if event == _e.GlossMergeAttempt:
            item = tuple(
                template_data.get(k) for k in ["term", "language", "t", "pos", "q"]
            )
            keys = [
                (
                    node.sense_idx,
                    gloss.text,
                    gloss.pos,
                    tuple(gloss.labels) if gloss.labels else None,
                )
                for gloss in node.glosses
            ]
            for key in keys:
                self.items[key].add(item)

        elif event in {_e.EtymIdMatch, _e.EtymIdOther} and with_gloss:
            item = tuple(
                template_data.get(k) for k in ["term", "language", "t", "pos", "q"]
            )
            keys = [
                (
                    node.sense_idx,
                    gloss.text,
                    gloss.pos,
                    tuple(gloss.labels) if gloss.labels else None,
                    int(event == _e.EtymIdMatch),
                )
                for gloss in node.glosses
            ]
            for key in keys:
                self.auto_items_etym[key].add(item)

        elif event == _e.SenseId and with_gloss:
            item = tuple(
                template_data.get(k) for k in ["term", "language", "t", "pos", "q"]
            )
            id_ = template_data.get("id")
            for gloss in node.glosses:
                key = (
                    node.sense_idx,
                    gloss.text,
                    gloss.pos,
                    tuple(gloss.labels) if gloss.labels else None,
                    int(gloss.id == id_),
                )
                self.auto_items_sense[key].add(item)


class GlossSimilarityItemCollector:
    class MatcherMock(GlossMatcherABC):
        def select(
            self, template_gloss: str, definitions: List[Tuple[LexemeBase, List[str]]]
        ) -> LexemeBase:
            return definitions[0][0]

    def __init__(self, wiktionary: Wiktionary, cache=None):
        self.merge_listener = IdMergeListener()
        init_and_configure(
            wiktionary,
            gloss_matcher=self.MatcherMock(),
            merge_listener=self.merge_listener,
            cache=cache,
        )
        self.extractor = EtymologyExtractor(BaselineExtractor(ETYMOLOGY_SECTION))

    @property
    def items(self):
        return self._make_frame(self.merge_listener.items)

    @property
    def auto_items_etym(self):
        return self._make_frame(self.merge_listener.auto_items_etym, labeled=True)

    @property
    def auto_items_sense(self):
        return self._make_frame(self.merge_listener.auto_items_sense, labeled=True)

    @staticmethod
    def _make_frame(data, labeled=False):
        df = pd.DataFrame([(*k, *v) for k, values in data.items() for v in values])
        df.columns = (
            ["sense_idx", "definition", "def_pos", "def_labels"]
            + (["match"] if labeled else [])
            + [
                "term",
                "lang",
                "temp_gloss",
                "temp_pos",
                "temp_qual",
            ]
        )
        df = df[
            (["match"] if labeled else [])
            + [
                "temp_gloss",
                "definition",
                "lang",
                "term",
                "sense_idx",
                "def_pos",
                "def_labels",
                "temp_pos",
                "temp_qual",
            ]
        ]
        return df.sort_values(["lang", "term", "temp_gloss", "sense_idx", "definition"])

    def run(self, out_dir=".", head=None):
        """
        Collect a gold standard from the id mechanism, also collect all instances where template glosses have to be
        mapped to a definition

        :param out_dir: the path to write the collected data to (creates 4 files)
        """
        out_dir = Path(out_dir)
        logging.getLogger("Lexemes").setLevel(logging.INFO)
        self.extractor.collect_relations(progress=True, head=head)
        # the gold standard derived from the sense parameter
        gold_std_sense = self.auto_items_sense
        gold_std_sense.to_csv(
            out_dir / "gold_standard_sense.csv",
            quoting=csv.QUOTE_NONNUMERIC,
            index=False,
        )
        # the gold standard derived from the etym parameter
        gold_std_etym = self.auto_items_etym
        gold_std_etym.to_csv(
            out_dir / "gold_standard_etym.csv",
            quoting=csv.QUOTE_NONNUMERIC,
            index=False,
        )
        # all other template gloss - definition pairs
        unannotated = self.items
        unannotated.to_csv(
            out_dir / "disambiguation.csv", quoting=csv.QUOTE_NONNUMERIC, index=False
        )
        # a subset, for manual annotation
        annotate = (
            unannotated[["lang", "term"]]
            .drop_duplicates()
            .sample(1000, random_state=33)
        )
        keys = list(zip(annotate.lang, annotate.term))
        annotate = (
            unannotated.set_index(["lang", "term"])
            .loc[keys]
            .reset_index()[unannotated.columns]
        )
        (
            annotate.sort_values(["lang", "term", "temp_gloss", "sense_idx"]).to_csv(
                out_dir / "annotate.csv", index=False, quoting=csv.QUOTE_NONNUMERIC
            )
        )


def get_argmax_prediction(probabilities, test: pd.DataFrame):
    """
    Given the probabilities for each testitem, select for each template gloss the definition with the highest probability
    """
    t2 = test.reset_index()
    t2["probs"] = probabilities
    bg_cols = ["term", "lang", "temp_gloss", "definition"]
    prediction = (
        t2.groupby(["term", "lang", "temp_gloss"])
        .definition.agg(lambda defs: defs.loc[t2.loc[defs.index].probs.idxmax()])
        .reset_index()[bg_cols]
    )
    prediction["argmax"] = 1
    t2 = t2.merge(prediction, left_on=bg_cols, right_on=bg_cols, how="left")
    t2.argmax.fillna(0, inplace=True)
    return t2.argmax


def get_univariate_predictions(
    train_featurized: pd.DataFrame,
    train: pd.Series,
    test_featurized: pd.DataFrame,
    test: pd.DataFrame,
    cv=0,
):
    """
    Make univariate logistic regression models, optionally crossvalidated

    :return: pair of (models, predictions)
    """
    models = {}
    predictions = pd.DataFrame(
        columns=pd.MultiIndex.from_product(
            [train_featurized.columns, ["pairwise", "prob", "argmax"]]
        ),
        index=range(len(test.index)),
    )
    for col in train_featurized:
        train_ = train_featurized.loc[:, col].values.reshape(-1, 1)
        scaler = StandardScaler().fit(train_)
        test_ = test_featurized.loc[:, col].values.reshape(-1, 1)
        params = {
            "random_state": 33,
            "solver": "lbfgs",
            "multi_class": "ovr",
            "max_iter": 100,
            "class_weight": "balanced",
        }
        if cv:
            LR = LogisticRegressionCV(cv=cv, **params).fit(
                scaler.transform(train_), train.match
            )
        else:
            LR = LogisticRegressionCV(**params).fit(
                scaler.transform(train_), train.match
            )
        predictions[col, "pairwise"] = LR.predict(scaler.transform(test_))
        predictions[col, "prob"] = LR.predict_proba(scaler.transform(test_))[:, 1]
        predictions[col, "argmax"] = get_argmax_prediction(
            predictions[col, "prob"], test
        ).values
        models[col] = LR
    return models, predictions


# Multivariate model
def get_multivariate_predictions(
    train_featurized: pd.DataFrame,
    train: pd.DataFrame,
    test_featurized: pd.DataFrame,
    test: pd.DataFrame,
    features: List[str],
):
    train_ = train_featurized[features]
    scaler = StandardScaler().fit(train_)
    test_ = test_featurized[features]
    params = dict(
        Cs=10,
        cv=10,
        random_state=33,
        solver="lbfgs",
        multi_class="ovr",
        max_iter=100,
        class_weight="balanced",
    )
    LR = LogisticRegressionCV(**params)
    LR.fit(scaler.transform(train_), train.match)

    pairwise = LR.predict(scaler.transform(test_))
    probs = LR.predict_proba(scaler.transform(test_))[:, 1]
    argmax = get_argmax_prediction(probs, test)
    return (
        LR,
        scaler,
        pd.DataFrame({"pairwise": pairwise, "probs": probs, "argmax": argmax.values}),
    )


def get_evaluation(
    train_featurized: pd.DataFrame,
    train: pd.DataFrame,
    test_featurized: pd.DataFrame,
    test: pd.DataFrame,
    features: List[str],
):
    *_, predictions = get_multivariate_predictions(
        train_featurized, train, test_featurized, test, features
    )
    return evaluate_predictions(predictions, test)


def evaluate_predictions(predictions, test):
    evals = [
        (f"{pred}_{l}", compare, predictions[pred])
        for l, compare in [("pairwise", test.match), ("sense", test.sense_match)]
        for pred in ["pairwise", "argmax"]
    ]
    performance = pd.DataFrame(
        {
            label: precision_recall_fscore_support(compare, pred, average="binary")[:3]
            for label, compare, pred in evals
        },
        index=["prec", "rec", "f1"],
    )
    return performance


def featurize(defgloss, tempgloss, levenshtein=Levenshtein()):
    """
    Calculate all features for dev
    :param defgloss:
    :param tempgloss:
    :param levenshtein:
    :return:
    """
    ret = {}
    defgloss = defgloss.strip().lower()
    tempgloss = tempgloss.lower().strip()
    ret["char_eq"] = int(defgloss == tempgloss)
    ret["char_temp_in_def"] = int(tempgloss in defgloss)
    ret["char_def_in_temp"] = int(defgloss in tempgloss)
    char_lev = levenshtein(defgloss, tempgloss)
    ret["char_levenshtein"] = char_lev
    ret["char_levenshtein_co8"] = min(char_lev, 8)
    dws = [w.lower() for w in re.findall(r"\w+", defgloss)]
    tws = [w.lower() for w in re.findall(r"\w+", tempgloss)]
    seqmatcher = SequenceMatcher(a=defgloss, b=tempgloss, autojunk=False)
    ret["char_longest_match"] = seqmatcher.find_longest_match(
        0, len(defgloss), 0, len(tempgloss)
    ).size
    ret["char_ratio"] = seqmatcher.ratio()

    ret["word_eq"] = int(dws == tws)
    seqmatcher = SequenceMatcher(a=dws, b=tws, autojunk=False)
    ret["word_longest_match"] = seqmatcher.find_longest_match(
        0, len(dws), 0, len(tws)
    ).size
    ret["word_ratio"] = seqmatcher.ratio()
    ret["word_levenshtein"] = word_levenshtein = levenshtein(dws, tws)
    ret["word_levenshtein_co5"] = min(word_levenshtein, 5)
    dwss = set(dws)
    twss = set(tws)

    # Tversky Index
    t1 = len(dwss & twss)
    t2 = len(dwss - twss)
    t3 = len(twss - dwss)
    ret["word_temp_in_def"] = int(t3 == 0)
    ret["word_def_in_temp"] = int(t2 == 0)
    for alpha in np.linspace(0, 1, 51):
        ret[f"tversky_{alpha}"] = (
            (t1 / (t1 + alpha * t2 + (1 - alpha) * t3)) if t1 else 0
        )

    # Fuzzy Tversky Index
    ts = defaultdict(lambda: 0)
    ds = defaultdict(lambda: 0)
    for d, t in itertools.product(dwss, twss):
        lev = levenshtein(d, t)
        dist = 1 / (1 + lev)
        ds[d] = max(ds[d], dist)
        ts[t] = max(ts[t], dist)

    t1 = (sum(ds[w] for w in dwss) + sum(ts[w] for w in twss)) / 2
    t2 = sum(1 - ds[w] for w in dwss)
    t3 = sum(1 - ts[w] for w in twss)
    for alpha in np.linspace(0, 1, 51):
        ret[f"fuzzy_tversky_{alpha}"] = (
            (t1 / (t1 + alpha * t2 + (1 - alpha) * t3)) if t1 else 0
        )

    return pd.Series(ret)

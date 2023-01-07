import abc
import importlib.resources
import itertools
import pickle
import re
from collections import defaultdict
from difflib import SequenceMatcher
from enum import IntEnum
from typing import List, Tuple, Mapping

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from etymmap.graph import LexemeBase, Node


class GlossMatcherABC(abc.ABC):
    @abc.abstractmethod
    def select(
        self, template_gloss: str, definitions: List[Tuple[LexemeBase, List[str]]]
    ) -> LexemeBase:
        pass


class LogisticRegressionGlossMatcher(GlossMatcherABC):
    def __init__(self, model: LogisticRegression, scaler: StandardScaler):
        self.model = model
        self.scaler = scaler

    def select(self, template_gloss: str, definitions: List[Tuple[LexemeBase, str]]):
        featurized = pd.DataFrame.from_records(
            [
                self.featurize(template_gloss, definition)
                for _, definition in definitions
            ]
        )
        featurized = self.scaler.transform(featurized)
        probabilities = self.model.predict_proba(featurized)[:, 1]
        return definitions[probabilities.argmax()][0]

    @abc.abstractmethod
    def featurize(self, template_gloss: str, definition: str):
        pass


class GlossMergeListener:
    """
    Baseclass to track link disambiguation. If used as an instance, ignores all events.
    """

    class Event(IntEnum):
        GlossMergeAttempt = 1
        EtymIdMatch = 2
        EtymIdOther = 3
        SenseId = 4
        SingleMeaningStub = 5
        Only1Choice = 6
        Section = 7
        Only1POS = 8
        LabelOrQual = 9
        FirstInstance = 10

    def __call__(self, event: Event, template_data: Mapping, node: Node):
        pass


class Levenshtein:
    def __init__(self, maxlen=50):
        self.maxlen = maxlen
        self.matrix = np.zeros((maxlen, maxlen), dtype=int)
        self.matrix[:, 0] = np.arange(maxlen)
        self.matrix[0, :] = np.arange(maxlen)

    def __call__(self, s1, s2, cutoff=None):
        """
        Early failure levenshtein

        :param s1: a string / iterable
        :param s2: a string / iterable
        :param cutoff: the maximum difference until which to continue the algorithm
        :return: the difference, or -1 if cutoff was exceeded
        """
        cutoff = cutoff or self.maxlen
        xlen = len(s1) + 1
        ylen = len(s2) + 1
        if ylen > xlen:
            s1, s2 = s2, s1
            xlen, ylen = ylen, xlen
        if abs(xlen - ylen) > cutoff:
            return -1
        elif xlen > self.maxlen or ylen > self.maxlen:
            return -1
        for i in range(1, xlen):
            min_y = 0
            for j in range(1, ylen):
                self.matrix[i, j] = v = min(
                    self.matrix[i - 1, j] + 1,
                    self.matrix[i - 1, j - 1] + int(s1[i - 1] != s2[j - 1]),
                    self.matrix[i, j - 1] + 1,
                )
                min_y = min(min_y or cutoff + 1, v)
            if min_y > cutoff:
                return -1
        lev = self.matrix[xlen - 1, ylen - 1]
        if lev > cutoff:
            return -1
        return lev


class AllFeaturesGlossMatcher(LogisticRegressionGlossMatcher):
    def __init__(self):
        super().__init__(
            pickle.loads(
                importlib.resources.read_binary("etymmap.data", "all_features.model")
            ),
            pickle.loads(
                importlib.resources.read_binary("etymmap.data", "all_features.scaler")
            ),
        )
        self.levenshtein = Levenshtein()

    def featurize(self, template_gloss: str, definition: str):
        ret = {}
        defgloss = definition.strip().lower()
        tempgloss = template_gloss.lower().strip()
        ret["char_eq"] = int(defgloss == tempgloss)
        ret["char_temp_in_def"] = int(tempgloss in defgloss)
        ret["char_def_in_temp"] = int(defgloss in tempgloss)
        char_lev = self.levenshtein(defgloss, tempgloss)
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
        ret["word_levenshtein"] = word_levenshtein = self.levenshtein(dws, tws)
        ret["word_levenshtein_co5"] = min(word_levenshtein, 5)
        dwss = set(dws)
        twss = set(tws)
        # Tversky Index
        t1 = len(dwss & twss)
        t2 = len(dwss - twss)
        t3 = len(twss - dwss)
        ret["word_temp_in_def"] = int(t3 == 0)
        ret["word_def_in_temp"] = int(t2 == 0)
        alpha = 0.32
        ret[f"tversky_{alpha}"] = (
            (t1 / (t1 + alpha * t2 + (1 - alpha) * t3)) if t1 else 0
        )
        # Fuzzy Tversky Index
        ts = defaultdict(lambda: 0)
        ds = defaultdict(lambda: 0)
        for d, t in itertools.product(dwss, twss):
            lev = self.levenshtein(d, t)
            dist = 1 / (1 + lev)
            ds[d] = max(ds[d], dist)
            ts[t] = max(ts[t], dist)
        t1 = (sum(ds[w] for w in dwss) + sum(ts[w] for w in twss)) / 2
        t2 = sum(1 - ds[w] for w in dwss)
        t3 = sum(1 - ts[w] for w in twss)
        alpha = 0.06
        ret[f"fuzzy_tversky_{alpha}"] = (
            (t1 / (t1 + alpha * t2 + (1 - alpha) * t3)) if t1 else 0
        )
        return pd.Series(ret)


class NoFuzzyGlossMatcher(LogisticRegressionGlossMatcher):
    def __init__(self):
        super().__init__(
            pickle.loads(
                importlib.resources.read_binary("etymmap.data", "no_fuzzy.model")
            ),
            pickle.loads(
                importlib.resources.read_binary("etymmap.data", "no_fuzzy.scaler")
            ),
        )

    def featurize(self, template_gloss: str, definition: str):
        ret = {}
        defgloss = definition.strip().lower()
        tempgloss = template_gloss.lower().strip()
        ret["char_eq"] = int(defgloss == tempgloss)
        ret["char_temp_in_def"] = int(tempgloss in defgloss)
        ret["char_def_in_temp"] = int(defgloss in tempgloss)
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
        dwss = set(dws)
        twss = set(tws)
        # Tversky Index
        t1 = len(dwss & twss)
        t2 = len(dwss - twss)
        t3 = len(twss - dwss)
        ret["word_temp_in_def"] = int(t3 == 0)
        ret["word_def_in_temp"] = int(t2 == 0)
        alpha = 0.32
        ret[f"tversky_{alpha}"] = (
            (t1 / (t1 + alpha * t2 + (1 - alpha) * t3)) if t1 else 0
        )
        return pd.Series(ret)

import hashlib
import re
from typing import Tuple, List, Any, Union, Dict, Collection

import numpy as np
from dash import callback_context, html


def random_color(obj) -> Tuple:
    """
    Convert an object into a rgb-triple, based on it's hash
    """
    h = int(hashlib.sha1(str(obj).encode("utf-8")).hexdigest(), 16)
    rgb = []
    for i in range(3):
        rgb.append(h % 256)
        h >>= 8
    return tuple(rgb)


Options = List[Dict[str, Any]]


def to_options(values: Union[List[Any], Dict[str, str]]) -> Options:
    if isinstance(values, List):
        return [{"label": v, "value": v} for v in values]
    return [{"label": k, "value": v} for k, v in values.items()]


def get_trigger() -> Tuple[str, str]:
    return callback_context.triggered[0]["prop_id"].split(".")


def create_testdata(n=10, k=25):
    nodes = [
        {"data": {"id": str(i), "label": f"term{i}", "_color": random_color(i)}}
        for i in range(n)
    ]
    relationships = [
        {"data": {"source": str(i), "target": str(j), "_color": "red"}}
        for i, j in zip(
            np.random.choice(np.arange(n), k), np.random.choice(np.arange(n), k)
        )
    ]
    return [*nodes, *relationships]


def id_merge(d: dict, *ids: Union[str, dict]) -> dict:
    ret = dict(d)
    for id in ids:
        if isinstance(id, str):
            id = {"id": id}
        ret.update(id)
    return ret


def as_cypher_list(items: Collection):
    if not items:
        return "[]"
    items = ", ".join([f'"{i}"' for i in items])
    return f"[{items}]"


def get_node_ids(cyto_elements: List[dict]):
    return [int(e["data"]["id"]) for e in cyto_elements if "source" not in e["data"]]


def text2display(text):
    """
    Translate the html tags found in text into html components

    (Could be implemented more efficient)
    """
    ret = []
    lastpos = 0
    for t in re.finditer("(<i>(.*?)</i>|<b>(.*?)</b>|<br/>)", text):
        if t.start() > lastpos:
            ret.append(text[lastpos : t.start()])
        if t.group(0) == "<br/>":
            ret.append(html.Br())
        elif t.group(0).startswith("<i"):
            ret.append(html.I(text2display(t.group(2))))
        else:
            ret.append(html.B(text2display(t.group(3))))
        lastpos = t.end()
    if lastpos < len(text):
        ret.append(text[lastpos:])
    return ret

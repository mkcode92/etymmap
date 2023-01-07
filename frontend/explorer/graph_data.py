import json
from typing import Union

import dash_cytoscape as cyto
import dash_html_components as html
from dash import dcc

from consts import LAYOUTS, DEFAULT_LAYOUT, relation_tree
from cyto_elements import convert_family_tree, convert_relation_tree
from dbconsts import Consts
from utils import id_merge

cyto.load_extra_layouts()

etym_graph_style = [
    {
        "selector": "node",
        "style": {
            "label": "data(term)",
            "color": "data(_color)",
            "font-size": "28px",
            "text-valign": "center",
            "background-opacity": "0",
            "opacitiy": 0.9,
        },
    },
    {
        "selector": ".source",
        "style": {"font-weight": "bold", "font-size": "42px", "opacity": 1},
    },
    {
        "selector": ".agg",
        "style": {"opacity": 1, "font-size": "data(_size)"},
    },
    {
        "selector": "edge",
        "style": {
            "curve-style": "bezier",
            "line-color": "data(_color)",
            "target-arrow-color": "data(_color)",
            "opacity": ".5",
        },
    },
    {
        "selector": ".directed",
        "style": {
            "target-arrow-shape": "triangle",
        },
    },
]

data_graph_style = [
    {
        "selector": "node",
        "style": {
            "label": "data(label)",
            "font-size": "28px",
            "text-valign": "center",
            "background-opacity": "0",
            "shape": "cut-rectangle",
        },
    },
    {
        "selector": "edge",
        "style": {
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "opacity": ".5",
        },
    },
    {
        "selector": ".F",
        "style": {
            "color": "orange",
        },
    },
    {"selector": ".L", "style": {"color": "blue"}},
    {"selector": r"#\(\'Inuktitut\'\,\ \'iu\'\,\ \'L\')", "style": {"color": "green"}},
]


def initialized_graphs(etymology, languages, relations, dbconsts: Consts):
    etymology_graph = wrap_graph(
        etymology, [], stylesheet=etym_graph_style, interactive=True
    )
    language_tree = wrap_graph(
        languages,
        convert_family_tree(dbconsts.combined_language_tree),
        stylesheet=data_graph_style,
        layout={
            "name": "klay",
            "nodeDimensionsIncludeLabels": True,
            "klay": {
                "compactComponents": True,
                "aspectRatio": 1.6,
                "thoroughness": 20,
                "spacing": 10,
                "randomizationSeed": 1,
            },
        },
        hidden=True,
    )
    cyto_relation_tree = wrap_graph(
        relations,
        convert_relation_tree(relation_tree),
        stylesheet=data_graph_style,
        layout={
            "name": "dagre",
            "rankDir": "LR",
            "nodeDimensionsIncludeLabels": True,
        },
        hidden=True,
    )

    return html.Div(
        id="all-graph-container",
        children=[etymology_graph, language_tree, cyto_relation_tree],
    )


def wrap_graph(
    id_: str,
    elements=None,
    stylesheet=None,
    layout: Union[str, dict] = DEFAULT_LAYOUT,
    hidden=False,
    zoom=0.1,
    interactive=False,
):
    if isinstance(layout, str):
        layout = json.loads(LAYOUTS[layout])

    children = [
        cyto.Cytoscape(
            id=id_merge({"type": "graph"}, id_),
            layout=layout,
            stylesheet=stylesheet,
            elements=elements,
            zoom=zoom,
            maxZoom=8,
            minZoom=0.1,
            boxSelectionEnabled=True,
            style={
                "height": "95vh",
                "width": "100%",
                "display": "block",
            },
        )
    ]
    if interactive:
        children.extend(
            [
                dcc.Store(
                    id=id_merge({"type": "element-store"}, id_),
                    storage_type="session",
                    data=elements,
                ),
                dcc.Store(
                    id=id_merge({"type": "cypher-history"}, id_),
                    storage_type="session",
                    data=[],
                ),
            ]
        )

    return html.Div(
        id=id_merge({"type": "graph-container"}, id_),
        className="graph-container",
        children=children,
        hidden=hidden,
    )

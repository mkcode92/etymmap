import abc
from enum import Enum
from typing import List, Union

import dash_bootstrap_components as dbc
import dash_html_components as html
from dash import dcc

from consts import *
from etymmap.graph import RelationType
from utils import to_options, id_merge

button_defaults = dict(size="sm", outline=True)
dropdown_defaults = dict(
    multi=True, clearable=True, searchable=True, style=dict(minHeight="38px")
)

LABEL_DROPDOWN = "label-dropdown"


class SelectButton:
    type = "select-button"

    def __new__(cls, *args, id: Union[str, dict], selected=False, **kwargs):
        return dbc.Button(
            *args,
            id=id_merge({"type": cls.type}, id),
            color="primary" if selected else "secondary",
            **kwargs,
        )


class SelectButtons:
    type = "select-button-group"

    def __new__(cls, values: List, id: Union[str, dict], select_idx=None, **kwargs):
        ret = [
            SelectButton(
                v,
                id=id_merge({"type": cls.type}, id, {"idx": i}),
                selected=i == select_idx,
                **kwargs,
            )
            for i, v in enumerate(values)
        ]
        return ret


class GroupedComponent(abc.ABC):
    class ID(Enum):
        pass

    def __init__(self, group: str):
        self.group = group

    def gid(self, id: ID):
        return {"group": self.group, "id": id.name}

    def values(self, comp, coll=None):
        if coll is None:
            coll = {}
        if isinstance(comp, list):
            for c in comp:
                self.values(c, coll)
        elif isinstance(comp, dict):
            id_ = comp.get("id", {})
            if isinstance(id_, dict) and id_.get("group") == self.group:
                i = id_["id"]
                try:
                    key = self.ID[i]
                except KeyError:
                    return coll
                if id_.get("type") == SelectButton.type:
                    coll[key] = comp["color"] == "primary"
                elif id_.get("type") == SelectButtons.type:
                    if comp["color"] == "primary":
                        coll[key] = comp["children"]
                    return coll
                else:
                    coll[key] = comp.get("value")
            else:
                for k, v in comp.items():
                    self.values(v, coll)
        return coll

    @classmethod
    def has_any_value(cls, values):
        return True

    @property
    @abc.abstractmethod
    def component(self):
        pass


class NodeSelect(GroupedComponent):
    class ID(Enum):
        TERM_TEXT = 1
        TERM_NOT = 2
        TERM_REGEX = 3
        LANGUAGES = 4
        LANGUAGES_NOT = 5
        LANGUAGE_CHILDREN = 6
        SENSE_IDX = 7
        POS = 8
        POS_NOT = 9
        GLOSS = 10
        GLOSS_REGEX = 11
        GLOSS_LABELS = 12
        LABELS = 13
        LABELS_NOT = 14
        LABELS_JOINER = 15

    def __init__(self, group, dbconsts, attrs_disabled=False):
        super().__init__(group)
        self.dbconsts = dbconsts
        self.attrs_disabled = attrs_disabled

    @classmethod
    def has_any_value(cls, values):
        return any(
            values.get(k)
            for k in [
                cls.ID.TERM_TEXT,
                cls.ID.LANGUAGES,
                cls.ID.POS,
                cls.ID.GLOSS,
                cls.ID.GLOSS_LABELS,
                cls.ID.LABELS,
            ]
        )

    @property
    def component(self):
        children = [
            self.term_select,
            self.language_select,
            self.sense_idx_select,
            self.label_select,
        ]
        if not self.attrs_disabled:
            children[3:3] = [self.pos_select, self.gloss_select]
        return html.Div(id=self.group, children=children)

    @property
    def term_select(self):
        regex = self.gid(self.ID.TERM_REGEX)
        return dbc.InputGroup(
            [
                dbc.Col(
                    dbc.Input(
                        id=self.gid(self.ID.TERM_TEXT),
                        type="text",
                        placeholder="Term",
                    ),
                    width=9,
                ),
                SelectButton(NOT, id=self.gid(self.ID.TERM_NOT), **button_defaults),
                SelectButton(REGEX, id=regex, **button_defaults),
                dbc.Tooltip(
                    "Regex",
                    target=id_merge({"type": "select-button"}, regex),
                ),
            ],
        )

    @property
    def language_select(self):
        transitive = self.gid(self.ID.LANGUAGE_CHILDREN)
        return dbc.InputGroup(
            [
                dbc.Col(
                    dcc.Dropdown(
                        options=self.dbconsts.languages,
                        id=self.gid(self.ID.LANGUAGES),
                        placeholder="Languages",
                        **dropdown_defaults,
                    ),
                    width=9,
                ),
                SelectButton(
                    NOT, id=self.gid(self.ID.LANGUAGES_NOT), **button_defaults
                ),
                SelectButton(
                    TRANSITIVE,
                    id=transitive,
                    **button_defaults,
                ),
                dbc.Tooltip(
                    "Also search successor/children languages.",
                    id=self.gid(self.ID.LANGUAGE_CHILDREN),
                    target={"type": "select-button", **transitive},
                ),
            ]
        )

    @property
    def sense_idx_select(self):
        return dbc.Col(
            dbc.Input(
                type="number",
                placeholder="Sense",
                min=0,
                max=100,
                step=1,
                id=self.gid(self.ID.SENSE_IDX),
            ),
            width=4,
        )

    @property
    def pos_select(self):
        return dbc.InputGroup(
            [
                dbc.Col(
                    dcc.Dropdown(
                        options=self.dbconsts.pos,
                        id=self.gid(self.ID.POS),
                        placeholder="POS",
                        **dropdown_defaults,
                    ),
                    width=9,
                ),
                SelectButton(NOT, id=self.gid(self.ID.POS_NOT), **button_defaults),
            ],
            style=dict(width="100%"),
        )

    @property
    def gloss_select(self):
        return dbc.Col(
            [
                dbc.InputGroup(
                    [
                        dbc.Col(
                            dbc.Input(
                                id=self.gid(self.ID.GLOSS),
                                type="text",
                                placeholder="Gloss",
                            ),
                            width=9,
                        ),
                        SelectButton(
                            REGEX, id=self.gid(self.ID.GLOSS_REGEX), **button_defaults
                        ),
                    ]
                ),
                dbc.Col(
                    dcc.Dropdown(
                        options=self.dbconsts.gloss_labels,
                        id=self.gid(self.ID.GLOSS_LABELS),
                        placeholder="Gloss-Label",
                        **dropdown_defaults,
                    ),
                    width=12,
                ),
            ]
        )

    @property
    def label_select(self):
        return dbc.InputGroup(
            [
                dbc.Col(
                    dcc.Dropdown(
                        options=self.dbconsts.node_labels,
                        value=["Multiword"],
                        id=id_merge({"type": LABEL_DROPDOWN}, self.gid(self.ID.LABELS)),
                        placeholder="Labels",
                        **dropdown_defaults,
                    ),
                    width=8,
                ),
                SelectButton(
                    NOT,
                    selected=True,
                    id=self.gid(self.ID.LABELS_NOT),
                    **button_defaults,
                ),
                *SelectButtons(
                    [OR, AND],
                    id=self.gid(self.ID.LABELS_JOINER),
                    select_idx=0,
                    **button_defaults,
                ),
                dbc.Tooltip(
                    "Match any label",
                    target=id_merge(
                        {"type": "select-button-group", "idx": 0},
                        self.gid(self.ID.LABELS_JOINER),
                    ),
                ),
                dbc.Tooltip(
                    "Match all labels",
                    target=id_merge(
                        {"type": "select-button-group", "idx": 1},
                        self.gid(self.ID.LABELS_JOINER),
                    ),
                ),
            ]
        )


class RelationSelect(GroupedComponent):
    class ID(Enum):
        SELECT = 1
        NOT = 2
        TRANSITIVE = 3
        DEPTH = 4
        DIRECTION = 5
        LIMIT = 6
        SHOW_RELATIONS = 7
        SHOW_LANGUAGES = 8
        CLOSE_TREE_VIEW = 9

    @property
    def component(self):
        return html.Div(
            children=[
                self.relation_select,
                self.search_depth,
                self.direction,
                self.limit,
                self.show_trees,
            ],
            id=self.group,
        )

    @property
    def relation_select(self):
        return dbc.InputGroup(
            [
                dbc.Col(
                    dcc.Dropdown(
                        options=to_options(
                            [r.name for r in RelationType if r.name != "_ontology"]
                        ),
                        value=["ORIGIN"],
                        id=self.gid(self.ID.SELECT),
                        placeholder="Relations",
                        **dropdown_defaults,
                    ),
                    width=9,
                ),
                SelectButton(NOT, id=self.gid(self.ID.NOT), **button_defaults),
                SelectButton(
                    TRANSITIVE,
                    selected=True,
                    id=self.gid(self.ID.TRANSITIVE),
                    **button_defaults,
                ),
                dbc.Tooltip(
                    "Also search more specific types.",
                    id="relation-types-transitive-tooltip",
                    target={
                        "type": "select-button",
                        **self.gid(self.ID.TRANSITIVE),
                    },
                ),
            ]
        )

    @property
    def search_depth(self):
        return dbc.Row(
            dcc.Slider(
                0,
                12,
                step=1,
                value=1,
                marks={i: str(i) for i in range(0, 15, 3)},
                id=self.gid(self.ID.DEPTH),
            ),
            style=dict(margin="20px"),
        )

    @property
    def direction(self):
        return dbc.InputGroup(
            SelectButtons(
                [LEFT, UNDIRECTED, RIGHT],
                id=self.gid(self.ID.DIRECTION),
                select_idx=1,
                **button_defaults,
            ),
        )

    @property
    def limit(self):
        return dbc.InputGroup(
            [
                dbc.InputGroupText("LIMIT"),
                dbc.Input(
                    self.gid(self.ID.LIMIT),
                    type="number",
                    placeholder="LIMIT",
                    min=0,
                    value=10,
                    step=1,
                ),
            ],
        )

    @property
    def show_trees(self):
        return dbc.InputGroup(
            [
                dbc.InputGroupText(TREE),
                dbc.Button(
                    SHOW_LANGUAGE_TREE,
                    id=self.gid(self.ID.SHOW_LANGUAGES),
                    color="secondary",
                    style=dict(width="initial"),
                    **button_defaults,
                ),
                dbc.Button(
                    SHOW_RELATION_TREE,
                    id=self.gid(self.ID.SHOW_RELATIONS),
                    color="secondary",
                    style=dict(width="initial"),
                    **button_defaults,
                ),
            ]
        )


class NavBar(GroupedComponent):
    class ID(Enum):
        SIMPLE_SEARCH_TERM = 1
        SUBMIT_SEARCH = 2
        ADVANCED_SEARCH_TOGGLE = 3
        ONCLICK = 4
        ONCLICK_LABEL = 5
        ONCLICK_DETAILS = 6
        ONCLICK_PRUNE = 7
        ONCLICK_EXPAND = 8
        ONCLICK_USE_SUBGRAPH_CONFIG = 9
        LAYOUT_SELECT = 10
        DOWNLOAD = 11
        N_NODES = 12
        AGGREGATE_BUTTON = 13

    @property
    def component(self):
        return dbc.Navbar(
            id="navbar",
            children=dbc.Container(
                dbc.Row(
                    [
                        dbc.Col(self.simple_search, width=4),
                        dbc.Col(self.on_click, width=3),
                        dbc.Col(self.graph_layout),
                        dbc.Col(self.download),
                    ],
                    style=dict(width="100%"),
                )
            ),
        )

    @property
    def simple_search(self):
        return dbc.InputGroup(
            [
                dbc.Input(
                    id=self.gid(self.ID.SIMPLE_SEARCH_TERM),
                    value="cat",
                    type="search",
                    placeholder="Search for a term",
                    style=dict(minWidth="150px"),
                ),
                dbc.Button(
                    html.Div(DETAILS, style=dict(fontSize="150%", margin="-5px")),
                    id=self.gid(self.ID.ADVANCED_SEARCH_TOGGLE),
                ),
                dbc.Tooltip(
                    "Advanced",
                    target=self.gid(self.ID.ADVANCED_SEARCH_TOGGLE),
                ),
                dbc.Button(
                    "Search", id=self.gid(self.ID.SUBMIT_SEARCH), color="primary"
                ),
                dbc.Button(AGGREGATE, id=self.gid(self.ID.AGGREGATE_BUTTON)),
                html.Div(
                    id=self.gid(self.ID.N_NODES),
                    children=["Displaying 0 nodes"],
                    style=dict(fontSize="small"),
                ),
            ]
        )

    @property
    def on_click(self):
        return html.Div(
            [
                dbc.InputGroup(
                    [
                        dbc.InputGroupText(
                            html.Div("👆", style=dict(fontSize="150%", margin="-5px")),
                            id="hand",
                        ),
                        dbc.Tooltip("Action when clicking nodes", target="hand"),
                        *SelectButtons(
                            ONCLICK_LABELS,
                            id=self.gid(self.ID.ONCLICK),
                            select_idx=0,
                            **button_defaults,
                        ),
                    ]
                ),
                dbc.Checklist(
                    id=self.gid(self.ID.ONCLICK_USE_SUBGRAPH_CONFIG),
                    options=[
                        {
                            "label": "Use search config in expand.",
                            "value": True,
                        }
                    ],
                    value=[False],
                    switch=True,
                ),
            ]
        )

    @property
    def graph_layout(self):
        return dbc.InputGroup(
            [
                dbc.InputGroupText("Layout"),
                dbc.Col(
                    dcc.Dropdown(
                        id=self.gid(self.ID.LAYOUT_SELECT),
                        options=to_options(LAYOUTS),
                        value=LAYOUTS[DEFAULT_LAYOUT],
                        clearable=False,
                    )
                ),
            ]
        )

    @property
    def download(self):
        return html.Div(
            [
                dbc.DropdownMenu(
                    label="Download",
                    children=[
                        dbc.DropdownMenuItem(
                            id=id_merge(self.gid(self.ID.DOWNLOAD), {"item": f}),
                            children=f,
                        )
                        for f in [
                            "graph (json)",
                            "graph (xlsx)",
                            "cypher history",
                        ]
                    ],
                ),
                dcc.Download(self.gid(self.ID.DOWNLOAD)),
            ]
        )


class Aggregation(GroupedComponent):
    class ID(Enum):
        LABEL_TEXT = 1
        LABEL_CREATE_BUTTON = 2
        SELECTED_LABELS = 3
        LABEL_DELETE_BUTTON = 4
        LABEL_DELETE_CONFIRM = 5
        LABEL_RELOAD = 6
        INCLUDE_LANGUAGES = 7

    def __init__(self, group, dbconsts):
        super().__init__(group)
        self.labels = to_options(dbconsts.node_labels)

    @property
    def component(self):
        return dbc.Col(
            id=self.group,
            children=[self.create_label, self.select_labels, self.buttons],
        )

    @property
    def create_label(self):
        return dbc.InputGroup(
            [
                dbc.Input(
                    type="text",
                    pattern=r"[a-zA-Z]+",
                    id=self.gid(self.ID.LABEL_TEXT),
                    placeholder="Create Label",
                ),
                dbc.Button(
                    ADD, **button_defaults, id=self.gid(self.ID.LABEL_CREATE_BUTTON)
                ),
                dbc.Tooltip(
                    "Create Label for displayed graph",
                    target=self.gid(self.ID.LABEL_CREATE_BUTTON),
                ),
            ]
        )

    @property
    def select_labels(self):
        return dbc.InputGroup(
            [
                dbc.Col(
                    dcc.Dropdown(
                        id=id_merge(
                            {"type": LABEL_DROPDOWN}, self.gid(self.ID.SELECTED_LABELS)
                        ),
                        options=self.labels,
                        **dropdown_defaults,
                    )
                )
            ]
        )

    @property
    def buttons(self):
        return dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Button(
                            DELETE,
                            id=self.gid(self.ID.LABEL_DELETE_BUTTON),
                            type="submit",
                            **button_defaults,
                        ),
                        dbc.Tooltip(
                            "Delete selected labels in database",
                            target=self.gid(self.ID.LABEL_DELETE_BUTTON),
                        ),
                        dcc.ConfirmDialog(
                            id=self.gid(self.ID.LABEL_DELETE_CONFIRM),
                            message="Do you want to delete all selected node labels permanently?",
                        ),
                        dbc.Button(
                            RELOAD,
                            id=self.gid(self.ID.LABEL_RELOAD),
                            type="submit",
                            **button_defaults,
                        ),
                        dbc.Tooltip(
                            "Reload labels from the database",
                            target=self.gid(self.ID.LABEL_RELOAD),
                        ),
                    ],
                ),
                dbc.Col(
                    dbc.Checklist(
                        id=self.gid(self.ID.INCLUDE_LANGUAGES),
                        options=[
                            {
                                "label": "Group by language",
                                "value": True,
                            }
                        ],
                        value=[True],
                        switch=True,
                        style=dict(width="100%"),
                    ),
                ),
            ],
            justify="end",
        )


def create_sidebar(
    id_,
    source_select: NodeSelect,
    subgraph_select,
    target_select,
    relation_select,
    aggregation,
):
    return html.Div(
        dbc.Collapse(
            id=id_,
            children=[
                dbc.Tabs(
                    [
                        dbc.Tab(
                            label=select.group.capitalize(),
                            children=dbc.Card(dbc.CardBody(select.component)),
                        )
                        for select in [source_select, subgraph_select, target_select]
                    ],
                    style=dict(height="initial"),
                ),
                dbc.Card(dbc.CardBody(relation_select.component)),
                dbc.Card(dbc.CardBody(aggregation.component)),
            ],
        ),
        style=dict(position="absolute", maxWidth="25%", zIndex=10000),
    )


def create_details(container_id, details_id, details_close_id):
    return html.Div(
        dbc.Collapse(
            id=container_id,
            children=dbc.Card(
                [
                    dbc.CardHeader(
                        [
                            "Details",
                            dbc.Button(
                                "X",
                                id=details_close_id,
                                **button_defaults,
                                style={"float": "right"},
                            ),
                        ]
                    ),
                    dbc.CardBody(id=details_id),
                ]
            ),
        ),
        style={
            "position": "absolute",
            "right": "3%",
            "top": "10%",
            "maxWidth": "33%",
            "zIndex": 1000,
        },
    )

import argparse
import datetime
import json
import re
from dataclasses import dataclass
from typing import Optional

import dash_bootstrap_components as dbc
import dash_cytoscape as cyto
import dash_html_components as html
from dash import Dash, State, Input, Output, MATCH, ALL, dash, dcc
from dash.exceptions import PreventUpdate

from components import (
    NodeSelect,
    RelationSelect,
    NavBar,
    Aggregation,
    create_sidebar,
    create_details,
    LABEL_DROPDOWN,
)
from consts import (
    NODE_COUNT_MESSAGE,
    NOTHING_FOUND,
    STATUS_STYLE_WARNING,
    STATUS_STYLE_NORMAL,
    SHOW_DETAILS,
    PRUNE,
    EXPAND,
    PROTECTED_NODE_LABELS,
)
from cyto_elements import prune, combine_elements, to_cyto_elements
from dbconsts import Consts
from etymmap.specific import Specific
from export import to_export_json, to_export_excel
from graph_data import initialized_graphs
from neo4jconnector import Neo4jConnector, SearchTooBroad, Neo4jConfig, default_config
from utils import (
    get_trigger,
    to_options,
    get_node_ids,
    id_merge,
    text2display,
)

cyto.load_extra_layouts()


def create(neo_config: Neo4jConfig = default_config):
    app = Dash(
        title="Etymmap 2.0",
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        assets_folder="../assets",
    )

    #################################
    # Load graph-specific constants #
    #################################

    app.neo4j = Neo4jConnector(neo_config)

    with app.neo4j.new_session() as session:
        LANGUAGES = session.get_all_languages()
        POS = session.get_all_pos()
        GLOSS_LABELS = session.get_glosslabels()
        LABELS = session.get_node_labels()
        LABELS.remove("Word")

    dbconsts = Consts(LANGUAGES, POS, GLOSS_LABELS, LABELS)
    app.logger.info(
        f"Found {len(LANGUAGES)} languages, {len(POS)} pos, {len(GLOSS_LABELS)} gloss labels and {len(LABELS)} nodes labels."
    )

    ################################
    # Build the main subcomponents #
    ################################
    NAVBAR = "navbar"
    navbar = NavBar(NAVBAR)

    SEARCH_OPTIONS = "search-options"
    SOURCE, SUBGRAPH, TARGET = "source", "subgraph", "target"
    RELATIONS, AGGREGATION = "relations", "aggregation"
    source_select = NodeSelect(SOURCE, dbconsts)
    # we disable attr select here because it is not yet implemented
    subgraph_select = NodeSelect(SUBGRAPH, dbconsts, attrs_disabled=True)
    target_select = NodeSelect(TARGET, dbconsts)
    relation_select = RelationSelect(RELATIONS)
    aggregation = Aggregation(AGGREGATION, dbconsts)
    sidebar = create_sidebar(
        SEARCH_OPTIONS,
        source_select,
        subgraph_select,
        target_select,
        relation_select,
        aggregation,
    )

    DETAILS = "details"
    DETAILS_CONTAINER = "details-container"
    DETAILS_CLOSE = "details-close"
    details = create_details(DETAILS_CONTAINER, DETAILS, DETAILS_CLOSE)

    ETYMOLOGY_GRAPH = "etymology"
    LANGUAGE_TREE = "language_tree"
    RELATIONS_TREE = "relations_tree"
    graphs = initialized_graphs(
        ETYMOLOGY_GRAPH, LANGUAGE_TREE, RELATIONS_TREE, dbconsts
    )

    app.layout = html.Div([navbar.component, sidebar, graphs, details])

    #############
    # Callbacks #
    #############

    ###########
    # Utility #
    ###########

    @app.callback(
        Output({"type": "select-button", "group": MATCH, "id": MATCH}, "color"),
        Input({"type": "select-button", "group": MATCH, "id": MATCH}, "n_clicks"),
        State({"type": "select-button", "group": MATCH, "id": MATCH}, "color"),
        prevent_initial_call=True,
    )
    def cb_select_button_clicked(_, color):
        """
        Indent the clicked button
        """
        return "primary" if color == "secondary" else "secondary"

    @app.callback(
        Output(
            {"type": "select-button-group", "group": MATCH, "id": MATCH, "idx": ALL},
            "color",
        ),
        Input(
            {"type": "select-button-group", "group": MATCH, "id": MATCH, "idx": ALL},
            "n_clicks",
        ),
        State(
            {"type": "select-button-group", "group": MATCH, "id": MATCH, "idx": ALL},
            "id",
        ),
        prevent_initial_call=True,
    )
    def cb_select_button_group_clicked(_, ids):
        trigger = get_trigger()
        trigger_id = json.loads(trigger[0])
        return ["primary" if i == trigger_id else "secondary" for i in ids]

    @app.callback(
        Output({"type": "graph", "id": ETYMOLOGY_GRAPH}, "elements"),
        Input({"type": "element-store", "id": ETYMOLOGY_GRAPH}, "data"),
        prevent_initial_call=True,
    )
    def update_graph(elements):
        return elements

    ######################
    # Basic interactions #
    ######################

    @app.callback(
        Output(SEARCH_OPTIONS, "is_open"),
        Output(navbar.gid(navbar.ID.SIMPLE_SEARCH_TERM), "disabled"),
        Input(navbar.gid(navbar.ID.ADVANCED_SEARCH_TOGGLE), "n_clicks"),
        State(SEARCH_OPTIONS, "is_open"),
        # prevent_initial_call=True,
    )
    def toggle_search_options(_, is_open):
        return not is_open, not is_open

    @app.callback(
        Output(aggregation.gid(aggregation.ID.LABEL_DELETE_BUTTON), "disabled"),
        Input(
            id_merge(
                {"type": LABEL_DROPDOWN},
                aggregation.gid(aggregation.ID.SELECTED_LABELS),
            ),
            "value",
        ),
    )
    def only_delete_when_possible(selected_labels):
        return not selected_labels

    @app.callback(
        Output(aggregation.gid(aggregation.ID.LABEL_DELETE_CONFIRM), "displayed"),
        Input(aggregation.gid(aggregation.ID.LABEL_DELETE_BUTTON), "n_clicks"),
        prevent_initial_call=True,
    )
    def ask_before_delete_labels(_):
        return True

    @app.callback(
        Output({"type": "graph-container", "id": ALL}, "hidden"),
        Output(relation_select.gid(relation_select.ID.SHOW_LANGUAGES), "color"),
        Output(relation_select.gid(relation_select.ID.SHOW_RELATIONS), "color"),
        Input(relation_select.gid(relation_select.ID.SHOW_LANGUAGES), "n_clicks"),
        Input(relation_select.gid(relation_select.ID.SHOW_RELATIONS), "n_clicks"),
        State({"type": "graph-container", "id": ALL}, "hidden"),
        prevent_initial_call=True,
    )
    def switch_tree_close_visibility(_, __, current_hidden):
        if json.loads(get_trigger()[0]) == relation_select.gid(
            relation_select.ID.SHOW_LANGUAGES
        ):
            if current_hidden[1]:
                return [True, False, True], "danger", "secondary"
        elif current_hidden[2]:
            return [True, True, False], "secondary", "danger"
        return [False, True, True], "secondary", "seondary"

    @app.callback(
        Output(navbar.gid(navbar.ID.DOWNLOAD), "data"),
        Input(id_merge(navbar.gid(navbar.ID.DOWNLOAD), {"item": ALL}), "n_clicks"),
        State({"type": "element-store", "id": ETYMOLOGY_GRAPH}, "data"),
        State({"type": "cypher-history", "id": ETYMOLOGY_GRAPH}, "data"),
        prevent_initial_call=True,
    )
    def download_data(_, current_elements: list, history: list):
        trigger = get_trigger()
        trigger_id = json.loads(trigger[0])["item"]
        if "graph" in trigger_id:
            node_ids = []
            rel_ids = []
            for d in current_elements:
                dd = d["data"]
                if "source" in dd:
                    rel_ids.append(dd["id"])
                else:
                    node_ids.append(dd["id"])
            nodes, relationships = session.export_selection(node_ids, rel_ids)
            format_ = re.match(r"\w+ \((\w+)\)", trigger_id).group(1)
            if format_ == "json":
                return dcc.send_string(
                    json.dumps(
                        to_export_json(nodes, relationships),
                        indent=2,
                    ),
                    "graph.json",
                )
            else:
                return {
                    "content": to_export_excel(nodes, relationships),
                    "filename": "graph.xlsx",
                    "base64": True,
                }
        return dcc.send_string("\n\n".join(history), "history.txt")

    ################################
    # `THE` Interactivity callback #
    ################################

    @app.callback(
        Output({"type": "element-store", "id": ETYMOLOGY_GRAPH}, "data"),
        Output({"type": "cypher-history", "id": ETYMOLOGY_GRAPH}, "data"),
        Output(navbar.gid(navbar.ID.N_NODES), "children"),
        Output(navbar.gid(navbar.ID.N_NODES), "style"),
        Output(DETAILS_CONTAINER, "is_open"),
        Output(DETAILS, "children"),
        Output({"type": "graph", "id": ETYMOLOGY_GRAPH}, "layout"),
        Output({"type": "label-dropdown", "group": ALL, "id": ALL}, "options"),
        Input(navbar.gid(navbar.ID.SUBMIT_SEARCH), "n_clicks"),
        Input(navbar.gid(navbar.ID.AGGREGATE_BUTTON), "n_clicks"),
        Input(navbar.gid(navbar.ID.LAYOUT_SELECT), "value"),
        Input({"type": "graph", "id": ETYMOLOGY_GRAPH}, "tapNodeData"),
        Input({"type": "graph", "id": ETYMOLOGY_GRAPH}, "tapEdgeData"),
        Input(aggregation.gid(aggregation.ID.LABEL_CREATE_BUTTON), "n_clicks"),
        Input(aggregation.gid(aggregation.ID.LABEL_DELETE_CONFIRM), "submit_n_clicks"),
        Input(aggregation.gid(aggregation.ID.LABEL_RELOAD), "n_clicks"),
        Input(DETAILS_CLOSE, "n_clicks"),
        State(NAVBAR, "children"),
        State(navbar.gid(navbar.ID.SIMPLE_SEARCH_TERM), "disabled"),
        State(SOURCE, "children"),
        State(SUBGRAPH, "children"),
        State(TARGET, "children"),
        State(RELATIONS, "children"),
        State(AGGREGATION, "children"),
        State({"type": "label-dropdown", "group": ALL, "id": ALL}, "options"),
        State(
            id_merge(
                {"type": LABEL_DROPDOWN},
                aggregation.gid(aggregation.ID.SELECTED_LABELS),
            ),
            "options",
        ),
        State({"type": "element-store", "id": ETYMOLOGY_GRAPH}, "data"),
        State({"type": "cypher-history", "id": ETYMOLOGY_GRAPH}, "data"),
    )
    def interact_graph(
        _submit_search,
        _aggregate_button,
        new_layout,
        node_tap,
        edge_tap,
        _create_labels,
        _delete_labels,
        _reload_labels,
        _close_details,
        navbar_state,
        simple_search_disabled,
        source_state,
        subgraph_state,
        target_state,
        relations_state,
        aggregation_state,
        all_label_dropdowns,
        current_labels,
        current_elements,
        current_history,
    ):
        trigger = get_trigger()
        new_layout = json.loads(new_layout)

        app.logger.debug(f"Interaction trigger: {trigger}")

        # helper to create return tuples with only the relevant outputs
        def ret(
            graph_data=dash.no_update,
            history=dash.no_update,
            status=dash.no_update,
            status_style=dash.no_update,
            show_details=dash.no_update,
            details_component=dash.no_update,
            layout=dash.no_update,
            updated_labels=dash.no_update,
        ):
            return (
                graph_data,
                history,
                status,
                status_style,
                show_details,
                details_component,
                layout,
                tuple(updated_labels for _ in all_label_dropdowns),
            )

        if trigger[0] == DETAILS_CLOSE:
            return ret(show_details=False)

        # initial search query
        if not trigger[0]:
            trigger_id = ""
        else:
            # for all other inputs we expect json as ids
            trigger_id = json.loads(trigger[0])

        # make the condition better readable
        (
            DO_SEARCH,
            AGGREGATE,
            CREATE_LABEL,
            DELETE_LABEL,
            RELOAD_LABEL,
            CHANGE_LAYOUT,
            GRAPH_TAP,
        ) = [
            id_ == trigger_id
            for id_ in [
                navbar.gid(navbar.ID.SUBMIT_SEARCH),
                navbar.gid(navbar.ID.AGGREGATE_BUTTON),
                aggregation.gid(aggregation.ID.LABEL_CREATE_BUTTON),
                aggregation.gid(aggregation.ID.LABEL_DELETE_CONFIRM),
                aggregation.gid(aggregation.ID.LABEL_RELOAD),
                navbar.gid(navbar.ID.LAYOUT_SELECT),
                {"type": "graph", "id": ETYMOLOGY_GRAPH},
            ]
        ]

        if CHANGE_LAYOUT:
            return ret(layout=new_layout)

        if any([AGGREGATE, CREATE_LABEL, DELETE_LABEL, RELOAD_LABEL]):
            aggregation_values = aggregation.values(aggregation_state)
            new_label_text = aggregation_values[aggregation.ID.LABEL_TEXT]
            selected_labels = aggregation_values[aggregation.ID.SELECTED_LABELS]
            include_languages = aggregation_values[aggregation.ID.INCLUDE_LANGUAGES]
            with app.neo4j.new_session() as session:
                if AGGREGATE:
                    nodes, relationships = session.aggregate(
                        selected_labels, include_languages
                    )
                    elements, size = to_cyto_elements(nodes, relationships, [])
                    return ret(
                        graph_data=elements,
                        status=NODE_COUNT_MESSAGE.format(size),
                        status_style=STATUS_STYLE_NORMAL,
                    )
                if CREATE_LABEL:
                    if not re.fullmatch("[a-zA-z]+", new_label_text):
                        return ret(
                            status="Invalid label name",
                            status_style=STATUS_STYLE_WARNING,
                        )
                    session.create_node_label(
                        new_label_text, get_node_ids(current_elements)
                    )
                    return ret(
                        status=f"Created label {new_label_text}",
                        status_style=STATUS_STYLE_NORMAL,
                        updated_labels=current_labels
                        + [{"label": new_label_text, "value": new_label_text}],
                    )
                elif DELETE_LABEL:
                    if not selected_labels:
                        raise PreventUpdate()
                    session.delete_node_labels(selected_labels)
                    return ret(
                        updated_labels=[
                            l
                            for l in current_labels
                            if not l["value"]
                            in set(selected_labels).difference(PROTECTED_NODE_LABELS)
                        ]
                    )
                elif RELOAD_LABEL:
                    all_current_labels = session.get_node_labels()
                    return ret(updated_labels=to_options(all_current_labels))

        navbar_values = navbar.values(navbar_state)
        event_data = None

        if GRAPH_TAP:
            onclick_action = navbar_values[navbar.ID.ONCLICK]

            event = trigger[1]
            event_data = node_tap if event == "tapNodeData" else edge_tap

            if onclick_action == SHOW_DETAILS:
                return ret(
                    show_details=True, details_component=render_element(event_data)
                )

            elif onclick_action == PRUNE:
                update_node_data, new_count = prune(event_data, current_elements)
                return ret(
                    graph_data=update_node_data,
                    status=NODE_COUNT_MESSAGE.format(new_count),
                    status_style=STATUS_STYLE_NORMAL,
                )

            elif onclick_action == EXPAND and event == "tapNodeData":
                DO_SEARCH = True
            else:
                # do not expand on relation click
                raise PreventUpdate()

        if DO_SEARCH or not trigger_id:
            simple_search_term = navbar_values[navbar.ID.SIMPLE_SEARCH_TERM]
            expand_use_config = navbar_values[navbar.ID.ONCLICK_USE_SUBGRAPH_CONFIG]
            node_id = event_data["id"] if event_data else None
            try:
                with app.neo4j.new_session() as session:
                    history_record = HistoryRecord(query_ts=datetime.datetime.utcnow())
                    if (
                        not simple_search_disabled
                        or event_data
                        and not expand_use_config
                    ):
                        nodes, relations, source_ids, query = session.simple_query(
                            simple_search_term, 10, node_id
                        )
                    else:
                        nodes, relations, source_ids, query = session.advanced_query(
                            source_select.values(source_state),
                            subgraph_select.values(subgraph_state),
                            target_select.values(target_state),
                            relation_select.values(relations_state),
                            dbconsts,
                            node_id,
                        )
                    history_record.query = query

            except SearchTooBroad as e:
                history_record.error = e.args[0]
                update_history(current_history, history_record)
                return ret(
                    status=e.args[0],
                    history=current_history,
                    status_style=STATUS_STYLE_WARNING,
                )

            elements, n_elements = to_cyto_elements(nodes, relations, source_ids)
            history_record.n_elements = n_elements
            update_history(current_history, history_record)
            if event_data:
                elements, n_elements = combine_elements(elements, current_elements)
            if not n_elements:
                return ret(
                    status=NOTHING_FOUND,
                    history=current_history,
                    status_style=STATUS_STYLE_WARNING,
                )
            return ret(
                graph_data=elements,
                history=current_history,
                status=NODE_COUNT_MESSAGE.format(n_elements),
                status_style=STATUS_STYLE_NORMAL,
            )

    @dataclass
    class HistoryRecord:
        query_ts: datetime.datetime
        query: Optional[str] = ""
        error: Optional[str] = None
        n_elements: int = 0

        def print(self):
            ret = [self.query_ts.strftime("%m-%d-%Y %H:%M:%S"), self.query]
            if self.error:
                ret.append(f"Error: {self.error}")
            else:
                ret.append(f"Found {self.n_elements} nodes")
            return "\n".join(ret)

    def update_history(current_history: list, record: HistoryRecord):
        current_history.append(record.print())

    def render_element(event_data):
        if "source" in event_data:
            lines = [f"### {event_data['type']}"]
            if event_data.get("unknown"):
                lines.append("* marked as uncertain")
            if event_data.get("text"):
                lines.append(f"* {event_data['text']}")
            if event_data.get("_count"):
                lines.append(f"* Count: {event_data['_count']}")
            return dcc.Markdown("\n".join(lines))

        if "born" in event_data:
            return dbc.Col(
                [
                    html.H3(event_data["term"]),
                    html.Ul(
                        [
                            html.Li([f"{label}: {event_data[key]}"])
                            for label, key in zip(
                                ["Born", "Died", "Occupation"], ["born", "died", "occ"]
                            )
                            if event_data[key]
                        ]
                    ),
                    *(
                        [html.A(event_data["wikipedia"])]
                        if event_data["wikipedia"]
                        else []
                    ),
                ]
            )

        else:
            if "term" in event_data:
                language = event_data.get("language", "")
                try:
                    language = Specific.language_mapper.code2name(language)
                except KeyError:
                    pass
                children = [
                    html.H3(f"{event_data['term']} ({language})"),
                    html.Br(),
                ]
                if int(event_data["id"]) < 1:
                    # aggregation
                    children.extend([html.B("Count:"), html.Div(event_data["_count"])])
                    children.extend(
                        [
                            html.B("Graph-Labels:"),
                            html.I(", ".join(event_data["labels"])),
                            html.Br(),
                        ]
                    )
                    return dbc.Col(children)

                # lexical nodes
                with app.neo4j.new_session() as session:
                    nodeid = int(event_data["id"])
                    attrs = session.get_node_attrs([nodeid])[nodeid]
                    labels = attrs["labels"]
                    etymology = attrs.get("etymology", "")
                    gloss_per_pos = attrs.get("gloss_per_pos")
                    pronunciation = attrs.get("pronunciation")

                children.extend(
                    [html.B("Graph-Labels:"), html.I(", ".join(labels)), html.Br()]
                )
                if pronunciation:
                    children.append(html.H4("Pronunciation"))
                    items = []
                    for pr in pronunciation:
                        ipa, kind, accent = [
                            pr.get(k) for k in ["ipa", "kind", "accent"]
                        ]
                        if kind == "phonemic":
                            ipa = f"/{ipa}/"
                        elif kind == "phonetic":
                            ipa = f"[{ipa}]"
                        if accent:
                            ipa = ipa + f" ({accent})"
                        items.append(html.Li(ipa))
                    children.append(html.Ul(items))
                if etymology:
                    children.append(html.H4("Etmyology"))
                    children.extend(text2display(etymology))
                if gloss_per_pos:
                    for pos, glosses in sorted(gloss_per_pos.items()):
                        children.append(html.H4(pos))
                        children.append(
                            html.Ul(
                                [
                                    html.Li(text2display(gloss["text"]))
                                    for gloss in glosses
                                ]
                            )
                        )

                return dbc.Col(children)
        return json.dumps(event_data, indent=2)

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--neo4j-config", required=False, help="Configuration for neo4j"
    )
    args = parser.parse_args()
    try:
        config = json.loads(args.neo4j_config) if args.neo4j_config else None
    except Exception as e:
        raise ValueError("Configuration must be provided in json format")
    app = create(Neo4jConfig(**config))
    app.run(port=8050, host="0.0.0.0")

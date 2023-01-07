import base64
from io import BytesIO

import pandas as pd


def attr_to_json(attrs: list) -> dict:
    return {k: v for k, v in dict(attrs).items() if k != "id"}


def get_gloss_json(attrs: list) -> list:
    return [attr_to_json(a) for a in attrs if "Gloss" in a.labels]


def get_pos_json(attrs: list) -> list:
    return [a["type"] for a in attrs if "POS" in a.labels]


def get_pronunc_json(attrs: list) -> list:
    return [attr_to_json(a) for a in attrs if "Pronunc" in a.labels]


def node_to_json(node, attrs):
    d = dict(node)
    d.update(
        {
            "id": node.id,
            "glosses": get_gloss_json(attrs),
            "pos": get_pos_json(attrs),
            "pronunciation": get_pronunc_json(attrs),
        }
    )
    return d


def rel_to_json(rel):
    return {
        "id": rel.id,
        "type": rel.type,
        "source": rel.start_node.id,
        "target": rel.end_node.id,
        **dict(rel),
    }


def to_export_json(nodes, relationships):
    return {
        "nodes": [node_to_json(node, attrs) for _, node, attrs in nodes],
        "relationships": [rel_to_json(r) for r in relationships[0]],
    }


def from_records_or_empty(
    data: list[dict], index: str, columns: list[str] = None
) -> pd.DataFrame:
    if data:
        return pd.DataFrame.from_records(data, index, columns)
    return pd.DataFrame(columns=columns, index=pd.Series(name=index, dtype=int))


def to_export_excel(nodes, relationships) -> str:
    node_data = []
    gloss_data = []
    pronunc_data = []
    entity_data = []
    for node_id, node, attrs in nodes:
        ndata = dict(node)
        ndata["id"] = node.id
        if "name" in ndata:
            entity_data.append(ndata)
            continue
        ndata["pos"] = ", ".join(get_pos_json(attrs))
        node_data.append(ndata)

        gdata = get_gloss_json(attrs)
        for g in gdata:
            g["node_id"] = node_id
        gloss_data.extend(gdata)

        pdata = get_pronunc_json(attrs)
        for p in pdata:
            p["node_id"] = node_id
        pronunc_data.extend(pdata)

    node_frame = from_records_or_empty(
        node_data,
        index="id",
    )
    gloss_frame = from_records_or_empty(
        gloss_data,
        index="node_id",
    )
    pronunc_frame = from_records_or_empty(
        pronunc_data,
        index="node_id",
    )
    entity_frame = from_records_or_empty(
        entity_data,
        index="id",
    )
    relations_frame = from_records_or_empty(
        [rel_to_json(r) for r in relationships[0]],
        index="id",
    )
    data = BytesIO()
    with pd.ExcelWriter(data, engine="xlsxwriter") as writer:
        node_frame.sort_values(["language", "term", "sense_idx"]).to_excel(
            writer, sheet_name="Lexemes"
        )
        relations_frame.to_excel(writer, sheet_name="Relationships")
        gloss_frame.sort_values("node_id").to_excel(writer, sheet_name="Glosses")
        pronunc_frame.sort_values("node_id").to_excel(
            writer, sheet_name="Pronunciation"
        )
        entity_frame.to_excel(writer, sheet_name="Entities")
    return base64.b64encode(data.getvalue()).decode()

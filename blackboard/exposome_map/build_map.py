#!/usr/bin/env python3
"""Build the exposome flow map from its Turtle source.

    python build_map.py            # reads exposome_map.ttl next to this script

Writes, next to the Turtle file:
    exposome_map.jsonld   the same graph as JSON-LD
    exposome_map.mmd      Mermaid flowchart
    exposome_map.svg      clickable SVG in blackboard style (white background)
    exposome_map.png      the SVG as an image, at twice its size (needs rsvg-convert)
    exposome_map.html     the SVG in a web page; hovering a node shows its ontology terms

If exposome_map_mappings.ttl exists it is read as part of the graph. Its
em:curatorMatch links (written by hand) and em:labelMatch links (written by
match_ontology.py) are the ontology terms shown in the page, curator matches first.
A label match that a curator rejected with em:curatorNoMatch is not shown.

Requires rdflib (Debian: python3-rdflib).

Every node in the SVG is a group with id = the local name of its IRI
(e.g. id="chem_6ppd"), a data-iri attribute and a <path class="node-box"> outline,
so data can later be mapped onto it by id. The link target of a node is its
skos:exactMatch / rdfs:seeAlso if it has one (for later ontology annotation),
otherwise its own IRI.
"""
import argparse
import html
import json
import math
import shutil
import subprocess
import zlib
from pathlib import Path

from urllib.parse import quote

from rdflib import Graph, Namespace, RDF, RDFS
from rdflib.namespace import SKOS, OWL

EM = Namespace("https://example.org/exposome-map/")
PORTAL = "https://expoportal.biohackeu.bigcat-bioinformatics.org"

# ---------------------------------------------------------------- model


def local(iri):
    return str(iri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def matches(g, n):
    """Ontology terms of a node: curator matches first, then the label matches that no curator
    chose. A label match that a curator rejected (em:curatorNoMatch) is left out."""
    curated = set(g.objects(n, EM.curatorMatch))
    rejected = set(g.objects(n, EM.curatorNoMatch))
    terms = [{"iri": str(m), "label": str(min(g.objects(m, RDFS.label), default=local(m))),
              "ontologies": sorted(str(a) for a in g.objects(m, EM.inOntology)), "curated": m in curated}
             for m in curated | (set(g.objects(n, EM.labelMatch)) - rejected)]
    return sorted(terms, key=lambda m: (not m["curated"], -len(m["ontologies"]), m["iri"]))


def load(ttl):
    g = Graph()
    g.parse(ttl, format="turtle")
    mappings = ttl.with_name(ttl.stem + "_mappings.ttl")
    if mappings.exists():
        g.parse(mappings, format="turtle")
    classes = {}
    for c in g.subjects(RDFS.subClassOf, EM.Node):
        classes[c] = {"label": str(g.value(c, RDFS.label)), "order": int(g.value(c, EM.stageOrder) or 99)}
    props = {}
    for p in g.subjects(RDF.type, OWL.ObjectProperty):
        props[p] = {
            "label": str(g.value(p, RDFS.label) or local(p)),
            "flow": bool(g.value(p, EM.flow)),
            "inferred": bool(g.value(p, EM.inferred)),
        }
    props[SKOS.broader] = {"label": "is a kind of", "flow": False, "inferred": False, "broader": True}
    nodes = {}
    for cls in classes:
        for n in g.subjects(RDF.type, cls):
            link = g.value(n, SKOS.exactMatch) or g.value(n, RDFS.seeAlso) or n
            nodes[n] = {
                "iri": str(n), "id": local(n), "cls": cls, "label": str(g.value(n, RDFS.label)),
                "definition": str(g.value(n, SKOS.definition) or ""),
                "alt": sorted(str(a) for a in g.objects(n, SKOS.altLabel)),
                "ink": str(g.value(n, EM.ink) or "orange"),
                "x": float(g.value(n, EM.x)) if g.value(n, EM.x) is not None else None,
                "y": float(g.value(n, EM.y)) if g.value(n, EM.y) is not None else None,
                "workflows": sorted(local(w) for w in g.objects(n, EM.inWorkflow)),
                "link": str(link),
                "matches": matches(g, n),
            }
    groups = {}  # group node -> member nodes
    for s, o in g.subject_objects(EM.hasPart):
        groups.setdefault(s, []).append(o)
    edges = []
    for s, p, o in g:
        if p in props and p not in (EM.hasPart, EM.inWorkflow) and s in nodes and o in nodes:
            edges.append((s, p, o))
    edges.sort(key=lambda e: (nodes[e[0]]["id"], local(e[1]), nodes[e[2]]["id"]))
    return g, classes, props, nodes, groups, edges


# ---------------------------------------------------------------- JSON-LD

def write_jsonld(g, path):
    context = {
        "em": str(EM), "rdfs": str(RDFS), "skos": str(SKOS), "owl": str(OWL),
        "dcterms": "http://purl.org/dc/terms/", "xsd": "http://www.w3.org/2001/XMLSchema#",
        "label": {"@id": "rdfs:label", "@language": "en"},
        "definition": {"@id": "skos:definition", "@language": "en"},
        "altLabel": {"@id": "skos:altLabel", "@language": "en"},
    }
    for p in sorted(set(g.predicates())):
        if str(p).startswith(str(EM)) and (p, RDF.type, OWL.ObjectProperty) in g:
            context[local(p)] = {"@id": "em:" + local(p), "@type": "@id"}
    context["broader"] = {"@id": "skos:broader", "@type": "@id"}
    context["hiddenLabel"] = {"@id": "skos:hiddenLabel", "@language": "en"}
    context["inOntology"] = "em:inOntology"
    data = json.loads(g.serialize(format="json-ld", context=context, auto_compact=True))
    # rdflib gives the nodes and the values in a different order on every run; sort them,
    # so that the file only changes when the graph changes
    order = lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False)
    for node in data["@graph"]:
        for key, value in node.items():
            if isinstance(value, list):
                value.sort(key=order)
    data["@graph"].sort(key=lambda node: (node.get("@id", ""), order(node)))
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- Mermaid

MERMAID_STYLE = {
    "Source": "fill:#e8f5e9,stroke:#2e7d32", "Emission": "fill:#f1f8e9,stroke:#558b2f",
    "Stressor": "fill:#fff3e0,stroke:#e65100", "ChemicalRole": "fill:#fffde7,stroke:#f9a825",
    "TransformationProcess": "fill:#fbe9e7,stroke:#bf360c", "ExposureRoute": "fill:#e3f2fd,stroke:#1565c0",
    "Organ": "fill:#e1f5fe,stroke:#0277bd", "Receptor": "fill:#e0f7fa,stroke:#00838f",
    "KeyEvent": "fill:#fce4ec,stroke:#ad1457", "AdverseOutcome": "fill:#ffebee,stroke:#b71c1c",
    "Modifier": "fill:#eceff1,stroke:#455a64", "OmicsMethod": "fill:#ede7f6,stroke:#4527a0",
    "ExposomeAssessment": "fill:#f3e5f5,stroke:#6a1b9a", "SamplingMethod": "fill:#f3e5f5,stroke:#6a1b9a",
    "Matrix": "fill:#f3e5f5,stroke:#6a1b9a", "AnalyticalMethod": "fill:#f3e5f5,stroke:#6a1b9a",
}


def write_mermaid(classes, props, nodes, groups, edges, path):
    def q(s):
        return '"' + s.replace('"', "#quot;") + '"'

    out = ["flowchart LR"]
    member_of = {m: grp for grp, ms in groups.items() for m in ms}
    by_class = {}
    for n, d in nodes.items():
        if n in groups or n in member_of:
            continue
        by_class.setdefault(d["cls"], []).append(n)
    for cls in sorted(by_class, key=lambda c: (classes[c]["order"], classes[c]["label"])):
        out.append(f"  subgraph cls_{local(cls)}[{q(classes[cls]['label'])}]")
        for n in sorted(by_class[cls], key=lambda n: nodes[n]["id"]):
            out.append(f"    {nodes[n]['id']}[{q(nodes[n]['label'])}]")
        out.append("  end")
    for grp, members in sorted(groups.items(), key=lambda kv: nodes[kv[0]]["id"]):
        out.append(f"  subgraph {nodes[grp]['id']}[{q(nodes[grp]['label'])}]")
        for n in sorted(members, key=lambda n: nodes[n]["id"]):
            out.append(f"    {nodes[n]['id']}[{q(nodes[n]['label'])}]")
        out.append("  end")
    out.append("")
    for s, p, o in edges:
        pr = props[p]
        arrow = "-.->" if (pr["inferred"] or pr.get("broader") or not pr["flow"]) else "-->"
        out.append(f"  {nodes[s]['id']} {arrow}|{q(pr['label'])}| {nodes[o]['id']}")
    out.append("")
    for name, style in MERMAID_STYLE.items():
        out.append(f"  classDef {name} {style},color:#111;")
    for n, d in sorted(nodes.items(), key=lambda kv: kv[1]["id"]):
        if n not in groups:
            out.append(f"  class {d['id']} {local(d['cls'])};")
    for n, d in sorted(nodes.items(), key=lambda kv: kv[1]["id"]):
        if n not in groups:
            tip = (d["definition"] or d["label"]).replace('"', "'")
            out.append(f"  click {d['id']} href {q(d['link'])} {q(tip)} _blank")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- SVG

COLW, ROWH = 178, 70          # grid unit in pixels
MARGIN_X, MARGIN_Y = 110, 150
INK = {"orange": "#e8590c", "purple": "#7b2fbe"}
FONT = "'Bradley Hand','Segoe Print','Chalkboard SE','Comic Sans MS','Patrick Hand',cursive"


def wrap(label, width=15):
    words, lines, cur = label.replace("-", "- ").split(), [], ""
    for w in words:
        glue = "" if cur.endswith("-") else " "
        if cur and len(cur) + len(glue) + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + glue + w) if cur else w
    lines.append(cur)
    return lines


def _bezier(p0, c1, c2, p3):
    """Sample a cubic Bezier roughly every 12 px."""
    n = max(4, int((abs(p3[0] - p0[0]) + abs(p3[1] - p0[1]) + abs(c1[0] - p0[0]) + abs(c2[1] - p3[1])) / 12))
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        pts.append((a * p0[0] + b * c1[0] + c * c2[0] + d * p3[0], a * p0[1] + b * c1[1] + c * c2[1] + d * p3[1]))
    return pts


def _round_rect(x, y, w, h, r):
    pts = []
    for cx, cy, a0 in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        for k in range(0, 91, 30):
            a = math.radians(a0 + k)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    out = []
    for i, p in enumerate(pts):          # densify the straight sides
        q = pts[(i + 1) % len(pts)]
        n = max(1, int(math.hypot(q[0] - p[0], q[1] - p[1]) / 14))
        out += [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(n)]
    return out


def rough(pts, key, amp=1.5, closed=False):
    """Hand-drawn wobble: a deterministic (per key) low-frequency offset along the line."""
    seed = zlib.crc32(key.encode())
    ph = [((seed >> (8 * i)) & 255) / 255 * 2 * math.pi for i in range(4)]
    out, s, total = [], 0.0, 0.0
    for a, b in zip(pts, pts[1:]):
        total += math.hypot(b[0] - a[0], b[1] - a[1])
    prev = pts[0]
    for p in pts:
        s += math.hypot(p[0] - prev[0], p[1] - prev[1])
        prev = p
        fade = 1.0 if closed else min(1.0, s / 14, max(0.0, total - s) / 14)
        dx = amp * fade * (math.sin(s / 31 + ph[0]) + 0.5 * math.sin(s / 11 + ph[1]))
        dy = amp * fade * (math.sin(s / 27 + ph[2]) + 0.5 * math.sin(s / 13 + ph[3]))
        out.append((p[0] + dx, p[1] + dy))
    if closed:
        mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        m0 = mid(out[-1], out[0])
        d = f"M{m0[0]:.1f},{m0[1]:.1f}"
        for i, p in enumerate(out):
            m = mid(p, out[(i + 1) % len(out)])
            d += f" Q{p[0]:.1f},{p[1]:.1f} {m[0]:.1f},{m[1]:.1f}"
        return d + " Z"
    d = f"M{out[0][0]:.1f},{out[0][1]:.1f}"
    for p, q in zip(out[1:-1], out[2:]):
        d += f" Q{p[0]:.1f},{p[1]:.1f} {(p[0] + q[0]) / 2:.1f},{(p[1] + q[1]) / 2:.1f}"
    return d + f" L{out[-1][0]:.1f},{out[-1][1]:.1f}"


def esc(s):
    return html.escape(str(s), quote=True)


def write_svg(classes, props, nodes, groups, edges, path):
    box = {}
    for n, d in nodes.items():
        if d["x"] is None:
            continue
        lines = wrap(d["label"])
        w = max(96, max(len(l) for l in lines) * 9.6 + 26)
        h = 22 * len(lines) + 16
        cx, cy = MARGIN_X + d["x"] * COLW, MARGIN_Y + d["y"] * ROWH
        box[n] = {"cx": cx, "cy": cy, "w": w, "h": h, "lines": lines}
    gbox = {}
    for grp, members in groups.items():
        ms = [box[m] for m in members if m in box]
        x0 = min(b["cx"] - b["w"] / 2 for b in ms) - 26
        x1 = max(b["cx"] + b["w"] / 2 for b in ms) + 26
        y0 = min(b["cy"] - b["h"] / 2 for b in ms) - 44
        y1 = max(b["cy"] + b["h"] / 2 for b in ms) + 22
        gbox[grp] = (x0, y0, x1, y1)

    # ---- edge geometry: pick ports, then spread edges that share a port
    def blocked(a, b):
        ax, ay, bx, by = box[a]["cx"], box[a]["cy"], box[b]["cx"], box[b]["cy"]
        for n, c in box.items():
            if n in (a, b):
                continue
            if abs(c["cx"] - ax) < 60 and min(ay, by) < c["cy"] < max(ay, by):
                return True
        return False

    plans = []
    for s, p, o in edges:
        if s not in box:
            continue
        a = box[s]
        if o in gbox:
            x0, y0, x1, y1 = gbox[o]
            if x0 < a["cx"] < x1:
                side_s = "b" if a["cy"] < y0 else "t"
                tgt = (a["cx"], y0 if a["cy"] < y0 else y1)
                side_t = "t" if a["cy"] < y0 else "b"
            elif a["cx"] <= x0:
                side_s, side_t = "r", "l"
                tgt = (x0, min(max(a["cy"], y0 + 20), y1 - 20))
            else:
                side_s, side_t = "l", "r"
                tgt = (x1, min(max(a["cy"], y0 + 20), y1 - 20))
            plans.append({"e": (s, p, o), "ss": side_s, "st": side_t, "tgt": tgt, "arc": False})
            continue
        if o not in box:
            continue
        b = box[o]
        dx, dy = b["cx"] - a["cx"], b["cy"] - a["cy"]
        if abs(dx) < 60:
            if blocked(s, o):
                plans.append({"e": (s, p, o), "ss": "l", "st": "l", "tgt": None, "arc": True})
            else:
                ss, st = ("b", "t") if dy > 0 else ("t", "b")
                plans.append({"e": (s, p, o), "ss": ss, "st": st, "tgt": None, "arc": False})
        else:
            ss, st = ("r", "l") if dx > 0 else ("l", "r")
            plans.append({"e": (s, p, o), "ss": ss, "st": st, "tgt": None, "arc": False})

    def port(n, side, off=0.0):
        b = box[n]
        if side == "l":
            return (b["cx"] - b["w"] / 2, b["cy"] + off)
        if side == "r":
            return (b["cx"] + b["w"] / 2, b["cy"] + off)
        if side == "t":
            return (b["cx"] + off, b["cy"] - b["h"] / 2)
        return (b["cx"] + off, b["cy"] + b["h"] / 2)

    share = {}
    for pl in plans:
        s, p, o = pl["e"]
        share.setdefault((s, pl["ss"]), []).append((pl, "s"))
        if o in box:
            share.setdefault((o, pl["st"]), []).append((pl, "t"))
    for (n, side), items in share.items():
        def other(item):
            pl, end = item
            s, p, o = pl["e"]
            m = o if end == "s" else s
            if m in box:
                c = box[m]
                return c["cy"] if side in "lr" else c["cx"]
            return pl["tgt"][1] if side in "lr" else pl["tgt"][0]
        items.sort(key=other)
        span = (box[n]["h"] if side in "lr" else box[n]["w"]) - 16
        step = min(11, span / max(1, len(items)))
        for i, (pl, end) in enumerate(items):
            pl["off_" + end] = (i - (len(items) - 1) / 2) * step

    def curve(pl):
        s, p, o = pl["e"]
        x1, y1 = port(s, pl["ss"], pl.get("off_s", 0))
        if pl["tgt"] is not None:
            x2, y2 = pl["tgt"]
            if pl["st"] in "lr":
                y2 = y1 if gbox[o][1] + 20 < y1 < gbox[o][3] - 20 else y2
            else:
                x2 = x1
        else:
            x2, y2 = port(o, pl["st"], pl.get("off_t", 0))
        if pl["arc"]:
            bulge = 58 + 0.12 * abs(y2 - y1)
            return (_bezier((x1, y1), (x1 - bulge, y1), (x2 - bulge, y2), (x2, y2)),
                    (x1 - bulge * 0.75, (y1 + y2) / 2))
        if pl["ss"] in "lr":
            k = max(24, abs(x2 - x1) * 0.45)
            sgn = 1 if pl["ss"] == "r" else -1
            d = _bezier((x1, y1), (x1 + sgn * k, y1), (x2 - sgn * k, y2), (x2, y2))
        else:
            k = max(14, abs(y2 - y1) * 0.45)
            sgn = 1 if pl["ss"] == "b" else -1
            d = _bezier((x1, y1), (x1, y1 + sgn * k), (x2, y2 - sgn * k), (x2, y2))
        return d, ((x1 + x2) / 2, (y1 + y2) / 2)

    xs = [b["cx"] for b in box.values()]
    ys = [b["cy"] for b in box.values()]
    W = int(max(xs) + MARGIN_X + 60)
    H = int(max(ys) + 110)

    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
             f'font-family="{FONT}" role="img" aria-labelledby="map-title">')
    o.append('<title id="map-title">Exposome flow map</title>')
    o.append(f"""<style>
  .node-box {{ fill: #fff; stroke-width: 2.4; }}
  .node text {{ font-size: 19px; text-anchor: middle; }}
  .ink-orange .node-box, .edge.ink-orange path {{ stroke: {INK['orange']}; }}
  .ink-purple .node-box, .edge.ink-purple path {{ stroke: {INK['purple']}; }}
  .ink-orange text {{ fill: {INK['orange']}; }}
  .ink-purple text {{ fill: {INK['purple']}; }}
  .edge path {{ fill: none; stroke-width: 2.2; stroke-linecap: round; }}
  .edge.inferred path {{ stroke-dasharray: 9 7; }}
  .edge.kind path {{ stroke-dasharray: 2 6; }}
  .edge.support path {{ stroke-width: 1.6; }}
  .edge text {{ font-size: 12px; text-anchor: middle; opacity: .8; paint-order: stroke; stroke: #fff; stroke-width: 4px; }}
  .group-box {{ fill: none; stroke-width: 3; }}
  .group text {{ font-size: 22px; }}
  a .node:hover .node-box {{ fill: #fff4e6; stroke-width: 3.6; }}
  a .node.ink-purple:hover .node-box {{ fill: #f3e8ff; }}
  .edge:hover path {{ stroke-width: 4; }}
  .match-dot {{ stroke: none; }}
  .ink-orange .match-dot {{ fill: {INK['orange']}; }}
  .ink-purple .match-dot {{ fill: {INK['purple']}; }}
  .caption {{ font-size: 15px; fill: #555; }}
  .title {{ font-size: 34px; fill: {INK['orange']}; }}
</style>""")
    o.append("<defs>")
    for name, col in INK.items():
        o.append(f'<marker id="head-{name}" viewBox="0 0 14 14" refX="12.5" refY="7" markerWidth="13" markerHeight="13" '
                 f'orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
                 f'<path d="M1.5,1.5 L12.5,7 L1.5,12.5 Z" fill="#fff" stroke="{col}" stroke-width="1.8" stroke-linejoin="round"/></marker>')
    o.append("</defs>")
    o.append(f'<rect id="background" width="{W}" height="{H}" fill="#fff"/>')
    o.append(f'<text class="title" x="{MARGIN_X - 70}" y="52">Exposome flow map</text>')

    # groups (brackets)
    o.append('<g id="groups">')
    for grp, (x0, y0, x1, y1) in gbox.items():
        d = nodes[grp]
        o.append(f'<a href="{esc(d["link"])}" target="_blank"><g id="{d["id"]}" class="group ink-{d["ink"]}{" has-match" if d["matches"] else ""}" data-iri="{esc(d["iri"])}" '
                 f'data-class="{local(d["cls"])}"><title>{esc(d["label"])} — {esc(d["definition"])}</title>'
                 f'<path class="group-box node-box" style="fill:none" d="{rough(_round_rect(x0, y0, x1 - x0, y1 - y0, 38), d["id"], 2.4, True)}"/>'
                 f'<text x="{x0 + 26:.1f}" y="{y1 - 16:.1f}">{esc(d["label"])}</text>'
                 + (f'<circle class="match-dot" cx="{x0 + 14:.1f}" cy="{y1 - 23:.1f}" r="3.6"/>' if d["matches"] else "")
                 + '</g></a>')
    o.append("</g>")

    # edges
    o.append('<g id="edges">')
    for pl in plans:
        s, p, t = pl["e"]
        pr = props[p]
        pts, (lx, ly) = curve(pl)
        ink = nodes[s]["ink"]
        cls = ["edge", f"ink-{ink}", "p-" + local(p)]
        cls.append("flow" if pr["flow"] else "support")
        if pr["inferred"]:
            cls.append("inferred")
        if pr.get("broader"):
            cls.append("kind")
        eid = f"edge__{nodes[s]['id']}__{local(p)}__{nodes[t]['id']}"
        tip = f"{nodes[s]['label']} — {pr['label']} → {nodes[t]['label']}"
        lab = "" if local(p) in ("leadsTo", "leadsToAOP") else \
            f'<text x="{lx:.1f}" y="{ly - 5:.1f}" fill="{INK[ink]}">{esc(pr["label"])}</text>'
        o.append(f'<g id="{eid}" class="{" ".join(cls)}" data-source="{nodes[s]["id"]}" data-target="{nodes[t]["id"]}" '
                 f'data-predicate="{esc(str(p))}"><title>{esc(tip)}</title>'
                 f'<path d="{rough(pts, eid)}" marker-end="url(#head-{ink})"/>{lab}</g>')
    o.append("</g>")

    # nodes
    o.append('<g id="nodes">')
    for n, b in sorted(box.items(), key=lambda kv: nodes[kv[0]]["id"]):
        d = nodes[n]
        cls = ["node", f"ink-{d['ink']}", "cls-" + local(d["cls"])] + ["wf-" + w for w in d["workflows"]]
        if d["matches"]:
            cls.append("has-match")
        tip = d["label"] + (f" ({', '.join(d['alt'])})" if d["alt"] else "") + f" — {classes[d['cls']]['label']}"
        if d["definition"]:
            tip += f". {d['definition']}"
        if d["matches"]:
            tip += f" [{len(d['matches'])} ontology term{'s' if len(d['matches']) > 1 else ''}]"
        o.append(f'<a href="{esc(d["link"])}" target="_blank"><g id="{d["id"]}" class="{" ".join(cls)}" '
                 f'data-iri="{esc(d["iri"])}" data-class="{local(d["cls"])}"><title>{esc(tip)}</title>')
        outline = _round_rect(b["cx"] - b["w"] / 2, b["cy"] - b["h"] / 2, b["w"], b["h"], 12)
        o.append(f'<path class="node-box" d="{rough(outline, d["id"], 1.3, True)}"/>')
        y = b["cy"] - (len(b["lines"]) - 1) * 11 + 6.5
        o.append(f'<text x="{b["cx"]:.1f}" y="{y:.1f}">' + "".join(
            f'<tspan x="{b["cx"]:.1f}" dy="{0 if i == 0 else 22}">{esc(l)}</tspan>' for i, l in enumerate(b["lines"])) + "</text>")
        if d["matches"]:
            o.append(f'<circle class="match-dot" cx="{b["cx"] + b["w"] / 2 - 9:.1f}" cy="{b["cy"] - b["h"] / 2 + 9:.1f}" r="3.2"/>')
        o.append("</g></a>")
    o.append("</g>")

    # legend
    lx, ly = MARGIN_X - 70, H - 176
    o.append(f'<g id="legend" class="caption" transform="translate({lx},{ly})">')
    rows = [("orange", "", "flow drawn on the board (orange)"),
            ("orange", "9 7", "link added from adverse outcome pathway knowledge"),
            ("purple", "", "annotation drawn on the board (purple)"),
            ("purple", "2 6", "is a kind of")]
    for i, (ink, dash, text) in enumerate(rows):
        o.append(f'<path d="M0,{i * 26} h70" stroke="{INK[ink]}" stroke-width="2.2" fill="none" '
                 f'stroke-dasharray="{dash}" marker-end="url(#head-{ink})"/>'
                 f'<text x="84" y="{i * 26 + 5}">{esc(text)}</text>')
    o.append(f'<circle cx="62" cy="{len(rows) * 26}" r="3.2" fill="{INK["orange"]}"/>'
             f'<text x="84" y="{len(rows) * 26 + 5}">node has ontology terms on ExpoPortal</text>')
    o.append(f'<text x="0" y="{len(rows) * 26 + 34}">Click a node to open its identifier; hover for its definition.</text>')
    o.append("</g>")
    o.append("</svg>")
    path.write_text("\n".join(o) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- HTML page

PAGE_CSS = """
:root{--bg:#fff;--fg:#1c1c1a;--muted:#6b6b66;--line:#dcdcd4;--panel:#fff;--accent:#1d5fa8;--hl:#fff4e6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,sans-serif}
header{padding:12px 16px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap}
header h1{font-size:18px;margin:0}header span{color:var(--muted);font-size:14px}
#map{overflow:auto;padding:8px 16px}
#map svg{display:block;max-width:none}
#map a{cursor:default}
#map .has-match{cursor:help}
#map a:focus{outline:none}
#map a:focus .node-box,#map .node.active .node-box{stroke-width:4.2}
#pop{position:absolute;z-index:10;width:max-content;max-width:min(440px,calc(100vw - 16px));max-height:380px;overflow:auto;
background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px;
box-shadow:0 6px 24px rgba(0,0,0,.25);font-size:14px}
#pop[hidden]{display:none}
#pop h3{margin:0;font-size:15px}
#pop .kind{color:var(--muted);font-size:12px}
#pop .def{margin:4px 0 8px}
#pop .id{color:var(--muted);font:12px ui-monospace,monospace;overflow-wrap:anywhere;margin-bottom:8px}
#pop h4{margin:8px 0 2px;font-size:13px}
#pop .cand{padding:6px 0;border-top:1px solid var(--line)}
#pop .lbl{font-weight:600}
#pop .how{color:var(--muted);font-size:12px;font-weight:400;border:1px solid var(--line);border-radius:10px;padding:0 8px;margin-left:6px;white-space:nowrap}
#pop .curated .how{color:var(--fg);background:var(--hl)}
#pop .iri{color:var(--muted);font:12px ui-monospace,monospace;overflow-wrap:anywhere}
#pop .links{display:flex;gap:6px;flex-wrap:wrap;margin-top:4px}
#pop .links a{color:var(--accent);border:1px solid var(--line);border-radius:10px;padding:0 8px;font-size:12px;text-decoration:none}
#pop .links a:hover,#pop .links a:focus{background:var(--hl)}
"""

PAGE_JS = r"""
const NODES = JSON.parse(document.getElementById('node-data').textContent);
const map = document.getElementById('map'), pop = document.getElementById('pop');
// the page shows its own popup, so drop the plain SVG tooltips of the nodes
map.querySelectorAll('.node > title, .group > title').forEach(t => t.remove());
let hideT, pinned = null, shown = null;
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text; return e; };
function show(g){
  clearTimeout(hideT);
  const d = NODES[g.id]; if (!d || !d.matches.length) return;   // no ontology term: no popup
  if (shown) shown.classList.remove('active');
  shown = g; g.classList.add('active');
  pop.replaceChildren(el('h3', '', d.label), el('div', 'kind', d.kind));
  if (d.definition) pop.append(el('div', 'def', d.definition));
  pop.append(el('div', 'id', d.iri));
  const n = d.matches.length;
  pop.append(el('h4', '', n + ' ontology term' + (n > 1 ? 's' : '') + ' on ExpoPortal'));
  for (const m of d.matches) {
    const c = el('div', m.curated ? 'cand curated' : 'cand'), k = el('div', 'links'), l = el('div', 'lbl', m.label);
    l.append(el('span', 'how', m.curated ? 'chosen by a curator' : 'matched on label'));
    for (const x of m.links) {
      const a = el('a', '', x.ont); a.href = x.url; a.target = '_blank'; a.rel = 'noopener';
      a.title = 'Open in ' + x.ont + ' on ExpoPortal'; k.append(a);
    }
    c.append(l, el('div', 'iri', m.iri), k); pop.append(c);
  }
  pop.hidden = false;
  const r = g.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
  const x = Math.min(Math.max(8, r.left), innerWidth - w - 8);
  let y = r.bottom + 6;
  if (y + h + 8 > innerHeight && r.top > h + 14) y = r.top - h - 6;
  pop.style.left = (x + scrollX) + 'px'; pop.style.top = (y + scrollY) + 'px';
}
function hideNow(){ pop.hidden = true; pinned = null; if (shown) shown.classList.remove('active'); shown = null; }
const hide = () => { if (!pinned) hideT = setTimeout(hideNow, 250); };
const target = e => e.target.closest ? e.target.closest('.node, .group') : null;
map.addEventListener('mouseover', e => { const g = target(e); if (g && !pinned) show(g); });
map.addEventListener('mouseout', e => { if (target(e)) hide(); });
map.addEventListener('focusin', e => { const g = target(e); if (g && !pinned) show(g); });
map.addEventListener('focusout', hide);
// a click keeps the popup open (the node identifiers are not web pages yet)
map.addEventListener('click', e => { const g = target(e); if (!g) return; e.preventDefault(); hideNow();
  if (NODES[g.id] && NODES[g.id].matches.length) { show(g); pinned = g; } });
pop.addEventListener('mouseenter', () => clearTimeout(hideT));
pop.addEventListener('mouseleave', hide);
document.addEventListener('click', e => { if (!e.target.closest('#pop') && !target(e)) hideNow(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideNow(); });
"""


def write_html(classes, nodes, svg_path, path):
    svg = svg_path.read_text(encoding="utf-8")
    data = {}
    for d in nodes.values():
        data[d["id"]] = {
            "label": d["label"] + (f" ({', '.join(d['alt'])})" if d["alt"] else ""),
            "kind": classes[d["cls"]]["label"], "definition": d["definition"], "iri": d["iri"],
            "matches": [{"label": m["label"], "iri": m["iri"], "curated": m["curated"],
                         "links": [{"ont": a, "url": f"{PORTAL}/ontologies/{a}?p=classes&conceptid={quote(m['iri'], safe='')}"}
                                   for a in m["ontologies"]]} for m in d["matches"]],
        }
    n_matched = sum(1 for d in data.values() if d["matches"])
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exposome flow map</title>
<style>{PAGE_CSS}</style>
</head>
<body>
<header><h1>Exposome flow map</h1>
<span>Nodes marked with a dot have ontology terms on ExpoPortal ({n_matched} of {len(data)}).
Hover or focus one to see them; click to keep the popup open.</span></header>
<div id="map">
{svg}</div>
<div id="pop" role="tooltip" hidden></div>
<script type="application/json" id="node-data">{payload}</script>
<script>{PAGE_JS}</script>
</body>
</html>
"""
    path.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ttl", nargs="?", default=here / "exposome_map.ttl", type=Path)
    args = ap.parse_args()
    g, classes, props, nodes, groups, edges = load(args.ttl)
    ids = [d["id"] for d in nodes.values()]
    assert len(ids) == len(set(ids)), "node identifiers are not unique"
    missing = [d["id"] for n, d in nodes.items() if n not in groups and d["x"] is None]
    assert not missing, f"nodes without layout hints: {missing}"
    stem = args.ttl.with_suffix("")
    write_jsonld(g, stem.with_suffix(".jsonld"))
    write_mermaid(classes, props, nodes, groups, edges, stem.with_suffix(".mmd"))
    write_svg(classes, props, nodes, groups, edges, stem.with_suffix(".svg"))
    print(f"{len(nodes)} nodes, {len(edges)} edges, {len(g)} triples")
    write_html(classes, nodes, stem.with_suffix(".svg"), stem.with_suffix(".html"))
    for ext in (".jsonld", ".mmd", ".svg", ".html"):
        print("wrote", stem.with_suffix(ext))
    if shutil.which("rsvg-convert"):
        subprocess.run(["rsvg-convert", "-z", "2", "-b", "white", str(stem.with_suffix(".svg")),
                        "-o", str(stem.with_suffix(".png"))], check=True)
        print("wrote", stem.with_suffix(".png"))
    else:
        print("rsvg-convert not found: no PNG written")


if __name__ == "__main__":
    main()

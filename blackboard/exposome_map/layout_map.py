#!/usr/bin/env python3
"""Give every node of the exposome map a place, in exposome_map_coordinates.ttl.

    python layout_map.py           # reads exposome_map.ttl next to this script

The coordinates file holds the layout hints of the nodes (em:x and em:y, in grid
units). A place that is already in the file is never changed, so the file can
be edited by hand to move a node. The script only adds a place for a node that
has none yet, at the end of the file:

  - to the right of a node that points to it, or to the left of a node it
    points to, in the same row;
  - else below the other nodes of its class;
  - else at the bottom left.

If the place is taken, the nearest free place above or below it is used. The
result is a reasonable first place, to be improved by hand where needed.
Groups (nodes with em:hasPart) are drawn around their members and get no place.

Requires rdflib (Debian: python3-rdflib). Run build_map.py afterwards.
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from rdflib import Graph, Namespace, RDF, RDFS
from rdflib.namespace import OWL, SKOS

EM = Namespace("https://example.org/exposome-map/")
ROW = 1.2                 # distance between two rows of nodes, in grid units
NEAR_X, NEAR_Y = 0.9, 1.0  # two nodes closer than this in both directions overlap
HEADER = """\
@prefix em: <https://example.org/exposome-map/> .

# =====================================================================
#  Places of the nodes on the exposome map (layout hints for the SVG)
#
#  em:x  column, em:y  row; in grid units, not pixels. One column is 178
#  pixels wide, one row 70 pixels high. Fractions are allowed.
#
#  layout_map.py ("make") adds a place for every node of exposome_map.ttl
#  that has none yet, at the end of this file. It never changes or removes
#  a line that is already here: edit this file by hand to move a node.
# =====================================================================

"""


def local(iri):
    return str(iri).rsplit("/", 1)[-1]


def free(x, y, places):
    return all(abs(x - px) >= NEAR_X or abs(y - py) >= NEAR_Y for px, py in places.values())


def nearest_free(x, y, places):
    """The place itself, or else the nearest free place below or above it."""
    x = max(x, 0.0)
    for step in range(40):
        for dy in ((0,) if step == 0 else (step * ROW, -step * ROW)):
            if y + dy >= 0 and free(x, y + dy, places):
                return round(x, 1), round(y + dy, 1)
    return round(x, 1), round(max(py for _, py in places.values()) + ROW, 1)


def place(n, g, places, links):
    """A place for node n, given the places of the other nodes."""
    before = sorted(s for s, o in links if o == n and s in places)     # nodes that point to n
    after = sorted(o for s, o in links if s == n and o in places)      # nodes that n points to
    if before:
        x, y = places[before[0]]
        return nearest_free(x + 1, y, places)
    if after:
        x, y = places[after[0]]
        return nearest_free(x - 1, y, places)
    same = [places[m] for c in g.objects(n, RDF.type) for m in g.subjects(RDF.type, c) if m in places]
    if same:
        x = Counter(px for px, _ in same).most_common(1)[0][0]         # the column most used by the class
        return nearest_free(x, max(py for px, py in same if px == x) + ROW, places)
    return nearest_free(0.0, max((py for _, py in places.values()), default=-ROW) + ROW, places)


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ttl", nargs="?", default=here / "exposome_map.ttl", type=Path)
    args = ap.parse_args()
    dest = args.ttl.with_name(args.ttl.stem + "_coordinates.ttl")

    g = Graph().parse(args.ttl, format="turtle")
    text = dest.read_text(encoding="utf-8") if dest.exists() else HEADER
    try:
        g.parse(data=text, format="turtle")
    except Exception as e:
        sys.exit(f"{dest} is not valid Turtle; nothing was changed.\n{e}")

    classes = set(g.subjects(RDFS.subClassOf, EM.Node))
    groups = set(g.subjects(EM.hasPart, None))
    nodes = sorted({n for c in classes for n in g.subjects(RDF.type, c)} - groups)
    places = {}
    for n in set(g.subjects(EM.x, None)) | set(g.subjects(EM.y, None)):
        x, y = g.value(n, EM.x), g.value(n, EM.y)
        if x is None or y is None:
            sys.exit(f"<{n}> has only one of em:x and em:y; nothing was changed.")
        places[n] = (float(x), float(y))
    for n in sorted(set(places) - set(nodes)):
        print(f"warning: {dest.name} has a place for <{n}>, which is not a node of the map", file=sys.stderr)

    props = set(g.subjects(RDF.type, OWL.ObjectProperty)) - {EM.hasPart, EM.inWorkflow} | {SKOS.broader}
    links = sorted((s, o) for s, p, o in g if p in props and s in nodes and o in nodes)
    todo = [n for n in nodes if n not in places]
    added = []
    while todo:
        # first the nodes that are linked to a node with a place, so that they end up next to it
        linked = [n for n in todo if any((s == n and o in places) or (o == n and s in places) for s, o in links)]
        n = (linked or todo)[0]
        todo.remove(n)
        places[n] = place(n, g, places, links)
        added.append(n)

    if not added and dest.exists():
        print(f"all {len(nodes)} nodes have a place; {dest.name} was not changed", file=sys.stderr)
        return
    if text and not text.endswith("\n"):
        text += "\n"
    for n in added:
        text += f"em:{local(n)} em:x {places[n][0]} ; em:y {places[n][1]} .   # placed by layout_map.py\n"
    Graph().parse(data=text, format="turtle")             # make sure the output is valid Turtle
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, dest)                                 # the old file stays whole if anything fails before this
    print(f"added a place for {len(added)} node(s): {', '.join(local(n) for n in added)}; wrote {dest}",
          file=sys.stderr)


if __name__ == "__main__":
    main()

# Rebuilds the files that are generated from the exposome map knowledge graph.
#
#   make          update the diagrams and index.html when they are out of date.
#                 A node without a place on the map gets one first, in
#                 exposome_map_coordinates.ttl; places that are already
#                 there are never changed.
#   make -B       rebuild them all (used by the GitHub Action, because a
#                 fresh checkout has no useful file times)
#   make match    look up the ontology terms on ExpoPortal and the chemical
#                 structures on Wikidata again. This writes the part of
#                 exposome_map_mappings.ttl below the marker line again; the
#                 part above it, written by hand, is kept.
#   make structures   only look up the chemical structures again (quick).
#
# "make match" and "make structures" only run when asked for by name: never as
# part of "make" or "make -B", and never in the GitHub Action.
#
# Needs GNU Make 4.3 or later, python3-rdflib and librsvg2-bin (rsvg-convert).

PYTHON   ?= python3
MAP_DIR  := blackboard/exposome_map
MAP      := $(MAP_DIR)/exposome_map
SOURCE   := $(MAP).ttl
MAPPINGS := $(MAP)_mappings.ttl
COORDS   := $(MAP)_coordinates.ttl
DIAGRAMS := $(MAP).jsonld $(MAP).mmd $(MAP).svg $(MAP).html $(MAP).png

.PHONY: all map match structures
.DELETE_ON_ERROR:
# The coordinates file is also edited by hand: never delete it when a step fails.
.PRECIOUS: $(COORDS)

all: map index.html

map: $(DIAGRAMS)

# Not a file rule on purpose: $(MAPPINGS) has no recipe, so make treats it as a
# source file and never regenerates it on its own, not even with -B.
match:
	$(PYTHON) $(MAP_DIR)/match_ontology.py $(SOURCE)

structures:
	$(PYTHON) $(MAP_DIR)/match_ontology.py --structures-only $(SOURCE)

# One run of build_map.py writes all diagrams. Without rsvg-convert it would
# silently skip the PNG, so check for it first.
# Places of the nodes. layout_map.py only adds a place for a node that has
# none, so this is safe to run at any time, also with -B.
$(COORDS): $(SOURCE) $(MAP_DIR)/layout_map.py
	$(PYTHON) $(MAP_DIR)/layout_map.py $(SOURCE)
	@touch $@

$(DIAGRAMS) &: $(SOURCE) $(COORDS) $(MAPPINGS) $(MAP_DIR)/build_map.py
	@command -v rsvg-convert >/dev/null || { echo "rsvg-convert not found (Debian: librsvg2-bin)" >&2; exit 1; }
	$(PYTHON) $(MAP_DIR)/build_map.py $(SOURCE)

# The page at the root of the repository is a copy of the map page.
index.html: $(MAP).html
	cp $< $@

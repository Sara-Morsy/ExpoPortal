# Rebuilds the files that are generated from the exposome map knowledge graph.
#
#   make          update the diagrams and index.html when they are out of date
#   make -B       rebuild them all (used by the GitHub Action, because a
#                 fresh checkout has no useful file times)
#   make match    look up the ontology terms on ExpoPortal again. This
#                 OVERWRITES exposome_map_mappings.ttl, including edits made
#                 by hand. It only runs when asked for by name: never as part
#                 of "make" or "make -B", and never in the GitHub Action.
#
# Needs GNU Make 4.3 or later, python3-rdflib and librsvg2-bin (rsvg-convert).

PYTHON   ?= python3
MAP_DIR  := blackboard/exposome_map
MAP      := $(MAP_DIR)/exposome_map
SOURCE   := $(MAP).ttl
MAPPINGS := $(MAP)_mappings.ttl
DIAGRAMS := $(MAP).jsonld $(MAP).mmd $(MAP).svg $(MAP).html $(MAP).png

.PHONY: all map match
.DELETE_ON_ERROR:

all: map index.html

map: $(DIAGRAMS)

# Not a file rule on purpose: $(MAPPINGS) has no recipe, so make treats it as a
# source file and never regenerates it on its own, not even with -B.
match:
	$(PYTHON) $(MAP_DIR)/match_ontology.py $(SOURCE)

# One run of build_map.py writes all diagrams. Without rsvg-convert it would
# silently skip the PNG, so check for it first.
$(DIAGRAMS) &: $(SOURCE) $(MAPPINGS) $(MAP_DIR)/build_map.py
	@command -v rsvg-convert >/dev/null || { echo "rsvg-convert not found (Debian: librsvg2-bin)" >&2; exit 1; }
	$(PYTHON) $(MAP_DIR)/build_map.py $(SOURCE)

# The page at the root of the repository is a copy of the map page.
index.html: $(MAP).html
	cp $< $@

# ExpoPortal

Repository for the BH project #19 at the BioHackathon Europe 2026.

## Updating the exposome map

The exposome map is described in three Turtle files in
[blackboard/exposome_map/](blackboard/exposome_map/):

- `exposome_map.ttl`: the nodes and links.
- `exposome_map_coordinates.ttl`: the place of each node on the map.
- `exposome_map_mappings.ttl`: the ontology terms per node.

The diagrams, the web page and `index.html` are generated from them. Do not
edit those by hand.

- **On GitHub.** When a change to a Turtle file is pushed to `main`, a GitHub
  Action rebuilds the generated files and commits them.
- **Locally.** Run `make` in the root of the repository. This needs GNU Make
  4.3 or later and the Debian packages `python3-rdflib` and `librsvg2-bin`.
- **Places.** A new node gets a place automatically. Places already in the
  coordinates file are never changed; edit that file to move a node.
- **Ontology terms.** `make match` looks up the node labels on ExpoPortal and
  the SMILES of ChEBI terms on Wikidata (`make structures` does only the
  latter). Matches made or rejected by hand (`em:curatorMatch`,
  `em:curatorNoMatch`) go above the marker line in the mappings file and are
  always kept; the part below it is written again. The GitHub Action never
  runs these.

See [blackboard/KG.md](blackboard/KG.md) for how the map is modelled.

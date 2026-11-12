# ExpoPortal

Repository for the BH project #19 at the BioHackathon Europe 2026.

## Updating the exposome map

The exposome map is described in two Turtle files in
[blackboard/exposome_map/](blackboard/exposome_map/): `exposome_map.ttl` (the
nodes and links) and `exposome_map_mappings.ttl` (the ontology terms per node).
The diagrams, the web page and `index.html` are generated from them. Do not
edit those by hand.

- **On GitHub.** When a change to one of the Turtle files is pushed to `main`,
  a GitHub Action rebuilds the generated files and commits them.
- **Locally.** Run `make` in the root of the repository. This needs GNU Make
  4.3 or later and the Debian packages `python3-rdflib` and `librsvg2-bin`.
- **Ontology terms.** `make match` looks up the node labels on ExpoPortal and
  writes the label matches in `exposome_map_mappings.ttl` again. Matches made
  or rejected by hand (`em:curatorMatch`, `em:curatorNoMatch`) go above the
  marker line in that file; that part is always kept. Lines changed by hand below the marker line are lost. The
  GitHub Action never runs `make match`.

See [blackboard/KG.md](blackboard/KG.md) for how the map is modelled.

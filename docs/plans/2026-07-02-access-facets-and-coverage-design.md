# Access facets & expanded home-region coverage — design

**Date:** 2026-07-02
**Status:** Approved

## Goal

Two improvements to The Exhibition Index:

1. **Comprehensive listings** for the home region and Amsterdam — raise per-city targets
   and give the weekly refresh explicit venue checklists.
2. **Structured filtering** — a first-class "access" facet (Museumkaart, free admission)
   filterable in the UI, replacing the ad-hoc `museumkaart` tag.

## Data schema

Each exhibition in `data/exhibitions.json` gains one optional field:

```json
"access": ["museumkaart"]
```

Controlled vocabulary: `museumkaart`, `free`, `pay-what-you-wish`.

- `museumkaart` — the show is at an Amsterdam Museumkaart member museum and covered by the card.
- `free` — the exhibition itself is free to enter (e.g. Smithsonian, NGA, BMA, Walters
  general admission). Ticketed special exhibitions at otherwise-free museums do **not**
  get the value.
- The existing `museumkaart` entries migrate from `tags` to `access`; `tags` stays
  free-form editorial vocabulary used only by search.

No show-type facet for now (retrospective/survey/etc.) — tags and search cover it; easy to
add later with the same pattern.

## UI (index.html)

- **Access filter group** in the sticky toolbar next to the status buttons:
  `All · Museumkaart · Free`, segmented-button style matching the status group, with live
  counts. Composes with city, status, saved, and search filters. Values with zero
  exhibitions site-wide are hidden (so `pay-what-you-wish` only appears once data uses it).
- **Row badge** — compact `MK` / `FREE` marker near the status tag, plus an "Access" line
  in the expanded detail panel.
- **Shareable URL state** — city, status, access, and search query sync to hash params
  (`#city=Amsterdam&access=museumkaart`), restored on load, written with `replaceState`
  (no history spam). Saved-only stays local (localStorage keys are device-specific).

## REFRESH.md (coverage policy)

- Venue checklists per home-region city, Amsterdam-style, with new targets:
  - **New York 12–18** — Met, MoMA, MoMA PS1, Whitney, Guggenheim, Brooklyn Museum, Frick,
    New Museum, Morgan Library, Neue Galerie, Jewish Museum, ICP, Noguchi, El Museo del
    Barrio, Asia Society, Bronx Museum, Dia Beacon & Storm King as day trips, plus notable
    galleries.
  - **Washington DC 10–15** — NGA, Hirshhorn, SAAM, Renwick, National Portrait Gallery,
    NMAA (Freer/Sackler), National Museum of African Art, Phillips Collection, NMWA,
    Kreeger, Glenstone, Rubell DC.
  - **Baltimore 8–14** — BMA, Walters, AVAM, the Peale, Reginald F. Lewis, Maryland Center
    for History & Culture, MICA & UMBC galleries, Creative Alliance, Baltimore Museum of
    Industry. (Smaller city: the "skip rather than pad with unverified entries" rule is the
    safety valve if fewer strong shows exist.)
  - **Philadelphia 5–8** — PMA, Barnes, PAFA, ICA Penn, Fabric Workshop and Museum.
  - **Amsterdam 10–15** — existing Museumkaart member-museum sweep.
- Schema docs updated with the `access` field, its vocabulary, and tagging rules
  (Museumkaart membership; free means the exhibition itself is free).

## Rollout

1. Schema migration + UI, verified against current 36 shows in local preview.
2. REFRESH.md rewrite.
3. Full research refresh to populate expanded listings (verified dates only).
4. Commit, push; confirm the Pages deploy actually goes live (deploy queue has been flaky).

## Error handling / testing

- UI treats `access` as optional — old data without the field renders unchanged.
- Unknown hash params are ignored; malformed values fall back to defaults.
- Verify with the preview tools: filter combinations, badge rendering, URL round-trip,
  mobile layout.

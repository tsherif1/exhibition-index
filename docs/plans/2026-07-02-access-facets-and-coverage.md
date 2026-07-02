# Access Facets & Expanded Coverage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a structured `access` facet (Museumkaart / free) with filter UI, badges, and shareable URL state, then expand home-region + Amsterdam coverage via REFRESH.md and a full data refresh.

**Architecture:** Single static page (`index.html`, vanilla JS, no build) reading `data/exhibitions.json`. All UI work is inline in index.html; coverage policy lives in REFRESH.md; data is produced by a web-research refresh following that policy.

**Tech Stack:** Vanilla HTML/CSS/JS, JSON data file, GitHub Pages via Actions. No test framework — verification is `python3 -m json.tool` for data and the local preview (`python3 -m http.server 4173`) for UI.

**Design doc:** `docs/plans/2026-07-02-access-facets-and-coverage-design.md`

---

### Task 1: Migrate `museumkaart` tag → `access` field

**Files:**
- Modify: `data/exhibitions.json`

**Step 1: Run the migration**

```bash
python3 - <<'EOF'
import json
p = "data/exhibitions.json"
d = json.load(open(p))
SMITHSONIAN_FREE = {"National Gallery of Art", "Hirshhorn Museum and Sculpture Garden",
  "Smithsonian American Art Museum", "National Portrait Gallery", "Renwick Gallery"}
for e in d["exhibitions"]:
    access = []
    if "museumkaart" in e.get("tags", []):
        e["tags"] = [t for t in e["tags"] if t != "museumkaart"]
        access.append("museumkaart")
    if any(v in e["venue"] for v in SMITHSONIAN_FREE):
        access.append("free")
    if access:
        e["access"] = access
json.dump(d, open(p, "w"), indent=2, ensure_ascii=False)
print("museumkaart:", sum(1 for e in d["exhibitions"] if "museumkaart" in e.get("access", [])))
print("free:", sum(1 for e in d["exhibitions"] if "free" in e.get("access", [])))
EOF
```

Only NGA + Smithsonian venues get `free` here (their exhibitions are reliably free);
BMA/Walters wait for the verified refresh in Task 5.

**Step 2: Verify**

Run: `python3 -m json.tool data/exhibitions.json > /dev/null && grep -c museumkaart data/exhibitions.json`
Expected: valid JSON; 9 museumkaart occurrences (all now inside `access`, none in `tags`).

**Step 3: Commit**

```bash
git add data/exhibitions.json
git commit -m "Migrate museumkaart tag to structured access field, mark free Smithsonian/NGA shows"
```

### Task 2: Access filter UI + row badges

**Files:**
- Modify: `index.html` (toolbar HTML ~line 486, CSS ~line 340, JS state/filter/render ~lines 521–611)

**Step 1: Add toolbar group** after the `#status-group` div:

```html
<div class="status-group" id="access-group">
  <button class="status-btn active" data-access="all">Any ticket</button>
</div>
```

Non-"all" buttons are rendered from data so vocabulary values with zero shows stay hidden.

**Step 2: Add JS**

- Labels: `const ACCESS_LABEL = { museumkaart: "Museumkaart", free: "Free", "pay-what-you-wish": "Pay what you wish" };`
  and `ACCESS_BADGE = { museumkaart: "MK", free: "FREE", "pay-what-you-wish": "PWYW" }`.
- `state.access = "all"`; filter line: `.filter(e => state.access === "all" || (e.access || []).includes(state.access))`.
- `renderAccess()` builds buttons with counts for each vocabulary value present in EXHIBITIONS; click handler mirrors the status group.
- Include access values in the search haystack.
- Row: wrap status column in `.status-cell` (flex column) and append `<span class="access-badge">` per value.
- Detail meta: add an "Access" line when `e.access` is present.

**Step 3: Add CSS** for `.status-cell` (column flex, gap 5px) and `.access-badge`
(9px uppercase, 1.2px klein border, klein text; hover-inverted like other cells).

**Step 4: Verify in preview**

Run local server, then: Museumkaart button shows (9), selecting it shows only Amsterdam
member-museum shows; Free shows the Smithsonian/NGA rows; badges render on rows and in
detail; composes with city/status/search; mobile layout intact.

**Step 5: Commit**

```bash
git add index.html
git commit -m "Add access facet filter, row badges, and detail line"
```

### Task 3: Shareable URL state

**Files:**
- Modify: `index.html` (JS only)

**Step 1: Implement**

- `syncHash()`: build `URLSearchParams` from non-default state (`city`, `status`, `access`, `q`), `history.replaceState(null, "", params.size ? "#" + params : location.pathname + location.search)`.
- `readHash()`: parse `location.hash.slice(1)` with URLSearchParams; validate city against data, status/access against known values; ignore anything malformed.
- Call `readHash()` after data loads (before first render); call `syncHash()` in each filter event handler. Saved-only stays out (device-local).

**Step 2: Verify in preview**

Set filters → hash updates; reload with `#city=Amsterdam&access=museumkaart` → filters restored, buttons active; garbage hash → defaults, no errors in console.

**Step 3: Commit**

```bash
git add index.html
git commit -m "Sync filters to shareable URL hash state"
```

### Task 4: REFRESH.md coverage rewrite

**Files:**
- Modify: `REFRESH.md`

**Step 1: Rewrite the refresh prompt** with per-city venue checklists and targets
(from the design doc): NYC 12–18, DC 10–15, Baltimore 8–14, Philadelphia 5–8,
Amsterdam 10–15, international cities unchanged (1–4 each). Keep all existing rules
(verified dates only, plain text, skip rather than pad).

**Step 2: Document the `access` field** in the schema section: vocabulary
(`museumkaart`, `free`, `pay-what-you-wish`), rules (Museumkaart member museums;
`free` only when the exhibition itself is free to enter), field optional.

**Step 3: Commit**

```bash
git add REFRESH.md
git commit -m "Coverage policy: venue checklists, deeper targets, access field rules"
```

### Task 5: Full research refresh

**Files:**
- Modify: `data/exhibitions.json`

**Step 1:** Run the REFRESH.md prompt: web research against museum sites/listings press,
verified dates only, `access` tagged per the new rules, `updated` set to today.

**Step 2: Verify**

`python3 -m json.tool` passes; per-city counts within target ranges (or honestly short
with strong entries only); spot-check several URLs resolve to official pages; every
Amsterdam member-museum show has `museumkaart`; free-venue shows have `free`.

**Step 3:** Reload preview: chips/counts/badges/filters all correct with the larger dataset.

**Step 4: Commit**

```bash
git add data/exhibitions.json
git commit -m "Full refresh: expanded NYC/DC/Baltimore/Philly/Amsterdam coverage with access facets"
```

### Task 6: Deploy and confirm live

**Step 1:** `git push`, watch the Pages workflow (`gh run watch` or `gh run list`).
The deploy queue has been flaky (see July 2 wedged deploy) — confirm the site actually
serves the new data (`curl -s https://tsherif1.github.io/exhibition-index/data/exhibitions.json | python3 -c "import json,sys; print(json.load(sys.stdin)['updated'])"`).

**Step 2:** Once live, delete the stale `pages-deploy-wedged` memory.

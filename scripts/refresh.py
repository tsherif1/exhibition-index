#!/usr/bin/env python3
"""Mechanical half of the weekly listings refresh.

    python3 scripts/refresh.py triage            # what needs research this week
    python3 scripts/refresh.py check --write     # validate + normalize formatting

The research rules and per-city targets live in REFRESH.md; this script reads the
targets from there so policy changes never need a code change.
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(ROOT, "data", "exhibitions.json")
REFRESH_MD = os.path.join(ROOT, "REFRESH.md")

FIELDS = ["title", "artist", "venue", "city", "start", "end", "tags", "access", "blurb", "note", "url"]
REQUIRED = [f for f in FIELDS if f != "access"]
LIST_FIELDS = {"tags", "access"}
ACCESS_VOCAB = {"museumkaart", "free", "pay-what-you-wish"}
TOP_LEVEL = ["updated", "method", "exhibitions"]

# REFRESH.md spells some cities differently from the data file.
CITY_ALIASES = {"Washington DC": "Washington, DC"}

# Venues whose general admission is free (REFRESH.md rule 6). A show there without
# `free` is only a warning: it may be separately ticketed.
FREE_VENUE_MARKERS = (
    "Smithsonian", "Hirshhorn", "Renwick", "National Portrait Gallery",
    "National Museum of Asian Art", "National Museum of African Art",
    "National Gallery of Art", "Baltimore Museum of Art", "Walters",
)

SOON_DAYS = 21
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------- targets

def parse_targets(md):
    """Return {city: (lo, hi)} from the venue-checklist bullets in REFRESH.md."""
    text = "\n".join(line.lstrip("> ").rstrip() for line in md.splitlines())
    targets = {}
    for m in re.finditer(r"\*\*([^*(]+?)\s*\((\d+)\s*[–-]\s*(\d+)[^)]*\):\*\*", text):
        city = CITY_ALIASES.get(m.group(1).strip(), m.group(1).strip())
        targets[city] = (int(m.group(2)), int(m.group(3)))
    m = re.search(r"international cities\s*\((\d+)\s*[–-]\s*(\d+)\s*each\):\s*(.+?)\.(?:\s|$)",
                  text, re.DOTALL)
    if m:
        rng = (int(m.group(1)), int(m.group(2)))
        for city in re.split(r",\s*", " ".join(m.group(3).split())):
            city = city.strip()
            if city:
                targets[CITY_ALIASES.get(city, city)] = rng
    return targets


def load_targets():
    try:
        with open(REFRESH_MD, encoding="utf-8") as f:
            return parse_targets(f.read())
    except OSError:
        return {}


# ---------------------------------------------------------------- helpers

def parse_date(s):
    if not isinstance(s, str) or not DATE_RE.match(s):
        return None
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def is_closed(show, today):
    end = parse_date(show.get("end"))
    return end is not None and end < today


def label(i, show):
    return '#%d "%s"' % (i + 1, show.get("title", "?") if isinstance(show, dict) else "?")


# ---------------------------------------------------------------- check

def check(data, today, targets):
    """Return (errors, warnings). Errors must be fixed before committing."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return ["top level must be an object"], []
    extra = [k for k in data if k not in TOP_LEVEL]
    missing = [k for k in TOP_LEVEL if k not in data]
    if extra:
        errors.append("unknown top-level field(s): %s" % ", ".join(extra))
    if missing:
        errors.append("missing top-level field(s): %s" % ", ".join(missing))
        return errors, warnings
    if parse_date(data["updated"]) is None:
        errors.append("updated must be YYYY-MM-DD")
    elif data["updated"] != today.isoformat():
        errors.append("updated is %s but today is %s" % (data["updated"], today.isoformat()))
    if not isinstance(data["method"], str) or not data["method"].strip():
        errors.append("method must be a non-empty string")
    elif "<" in data["method"] or ">" in data["method"]:
        errors.append("method contains markup")
    shows = data["exhibitions"]
    if not isinstance(shows, list):
        return errors + ["exhibitions must be a list"], warnings

    seen = {}
    counts = {}
    for i, s in enumerate(shows):
        lab = label(i, s)
        if not isinstance(s, dict):
            errors.append("%s: entry must be an object" % lab)
            continue
        for k in s:
            if k not in FIELDS:
                errors.append("%s: unknown field %r" % (lab, k))
        for k in REQUIRED:
            if k not in s:
                errors.append("%s: missing field %r" % (lab, k))
        for k, v in s.items():
            if k in LIST_FIELDS:
                if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                    errors.append("%s: %s must be a list of non-empty strings" % (lab, k))
                    continue
                strings = v
            else:
                if not isinstance(v, str) or not v.strip():
                    errors.append("%s: %s must be a non-empty string" % (lab, k))
                    continue
                strings = [v]
            if any("<" in x or ">" in x for x in strings):
                errors.append("%s: %s contains markup" % (lab, k))
        if "access" in s and isinstance(s["access"], list):
            bad = [a for a in s["access"] if a not in ACCESS_VOCAB]
            if bad:
                errors.append("%s: unknown access value(s) %s (allowed: %s)"
                              % (lab, ", ".join(map(str, bad)), ", ".join(sorted(ACCESS_VOCAB))))
        url = s.get("url")
        if isinstance(url, str) and not url.startswith("https://"):
            errors.append("%s: url must start with https://" % lab)
        start, end = parse_date(s.get("start")), parse_date(s.get("end"))
        if "start" in s and start is None:
            errors.append("%s: start must be YYYY-MM-DD" % lab)
        if "end" in s and end is None:
            errors.append("%s: end must be YYYY-MM-DD" % lab)
        if start and end and start > end:
            errors.append("%s: start %s is after end %s" % (lab, s["start"], s["end"]))
        if end and end < today:
            errors.append("%s: closed on %s (drop it)" % (lab, s["end"]))
        key = (s.get("title"), s.get("venue"))
        if key in seen:
            errors.append("%s: duplicate of %s" % (lab, seen[key]))
        seen.setdefault(key, lab)

        city = s.get("city")
        access = s.get("access") if isinstance(s.get("access"), list) else []
        if isinstance(city, str):
            if targets and city not in targets:
                warnings.append("%s: city %r is not in REFRESH.md's city list" % (lab, city))
            if city == "Amsterdam" and "museumkaart" not in access:
                warnings.append("%s: Amsterdam show without museumkaart access; confirm the venue is not a member" % lab)
            if not (end and end < today):
                counts[city] = counts.get(city, 0) + 1
        venue = s.get("venue")
        if isinstance(venue, str) and any(m in venue for m in FREE_VENUE_MARKERS) and "free" not in access:
            warnings.append("%s: %s is normally free; add free access unless this show is separately ticketed" % (lab, venue))

    for city, (lo, hi) in targets.items():
        n = counts.get(city, 0)
        if n < lo:
            warnings.append("%s under target: %d listed, REFRESH.md asks for %d-%d" % (city, n, lo, hi))
    return errors, warnings


# ---------------------------------------------------------------- triage

def triage(data, today, targets, soon_days=SOON_DAYS):
    shows = data.get("exhibitions", [])
    horizon = today + datetime.timedelta(days=soon_days)
    t = {"closed": [], "ending_soon": [], "opening_soon": [], "coverage": []}
    counts = {}
    for s in shows:
        start, end = parse_date(s.get("start")), parse_date(s.get("end"))
        if end and end < today:
            t["closed"].append(s)
            continue
        if end and end <= horizon:
            t["ending_soon"].append(s)
        if start and start > today:
            t["opening_soon"].append(s)
        counts[s.get("city")] = counts.get(s.get("city"), 0) + 1
    for city, rng in targets.items():
        n = counts.get(city, 0)
        t["coverage"].append({"city": city, "count": n, "target": rng, "under": n < rng[0]})
    for city, n in counts.items():
        if city not in targets:
            t["coverage"].append({"city": city, "count": n, "target": None, "under": False})
    return t


def render_triage(t, today):
    def row(s):
        return "  - %s | %s, %s | %s to %s" % (s.get("title"), s.get("venue"), s.get("city"), s.get("start"), s.get("end"))
    out = ["Refresh triage for %s" % today.isoformat(), ""]
    out.append("CLOSED - drop these (%d):" % len(t["closed"]))
    out += [row(s) for s in t["closed"]] or ["  (none)"]
    out += ["", "ENDING WITHIN %d DAYS - re-confirm the closing date, mark 'final weeks' in the note (%d):"
            % (SOON_DAYS, len(t["ending_soon"]))]
    out += [row(s) for s in t["ending_soon"]] or ["  (none)"]
    out += ["", "NOT YET OPEN - confirm the opening still stands (%d):" % len(t["opening_soon"])]
    out += [row(s) for s in t["opening_soon"]] or ["  (none)"]
    out += ["", "COVERAGE after dropping closed shows (research cities marked UNDER first):"]
    for c in t["coverage"]:
        tgt = "%d-%d" % c["target"] if c["target"] else "no target"
        flag = "  UNDER" if c["under"] else ""
        out.append("  %-16s %3d  (target %s)%s" % (c["city"], c["count"], tgt, flag))
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- format

def _s(v):
    return json.dumps(v, ensure_ascii=False)


def format_json(data):
    """House style: 2-space indent, arrays inline, one entry per object, UTF-8 as is."""
    lines = ["{"]
    items = list(data.items())
    for i, (k, v) in enumerate(items):
        last = i == len(items) - 1
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            lines.append('  "%s": [' % k)
            for j, e in enumerate(v):
                lines.append("    {")
                fields = list(e.items())
                for n, (fk, fv) in enumerate(fields):
                    val = "[" + ", ".join(_s(x) for x in fv) + "]" if isinstance(fv, list) else _s(fv)
                    lines.append('      "%s": %s%s' % (fk, val, "" if n == len(fields) - 1 else ","))
                lines.append("    }" + ("" if j == len(v) - 1 else ","))
            lines.append("  ]" + ("" if last else ","))
        else:
            lines.append('  "%s": %s%s' % (k, _s(v), "" if last else ","))
    lines.append("}")
    return "\n".join(lines) + "\n"


def normalize(data):
    """Canonical key order for the top level and each entry; unknown keys keep their place at the end."""
    out = {k: data[k] for k in TOP_LEVEL if k in data}
    out.update({k: v for k, v in data.items() if k not in out})
    if isinstance(out.get("exhibitions"), list):
        out["exhibitions"] = [
            dict(sorted(e.items(), key=lambda kv: FIELDS.index(kv[0]) if kv[0] in FIELDS else len(FIELDS)))
            if isinstance(e, dict) else e
            for e in out["exhibitions"]
        ]
    return out


# ---------------------------------------------------------------- cli

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("triage", "check"):
        p = sub.add_parser(name)
        p.add_argument("path", nargs="?", default=DEFAULT_DATA)
        p.add_argument("--today", help="YYYY-MM-DD (default: today)")
        if name == "check":
            p.add_argument("--write", action="store_true", help="rewrite the file in house formatting")
    args = ap.parse_args(argv)
    today = parse_date(args.today) if args.today else datetime.date.today()
    if today is None:
        ap.error("--today must be YYYY-MM-DD")
    with open(args.path, encoding="utf-8") as f:
        data = json.load(f)
    targets = load_targets()

    if args.cmd == "triage":
        sys.stdout.write(render_triage(triage(data, today, targets), today))
        return 0

    errors, warnings = check(data, today, targets)
    if args.write:
        with open(args.path, "w", encoding="utf-8") as f:
            f.write(format_json(normalize(data)))
    for w in warnings:
        print("WARN: " + w)
    for e in errors:
        print("ERROR: " + e)
    n = len(data.get("exhibitions", [])) if isinstance(data, dict) else 0
    print("%s: %d shows, %d error(s), %d warning(s)%s"
          % (os.path.relpath(args.path), n, len(errors), len(warnings), ", file rewritten" if args.write else ""))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

import datetime
import json
import os
import subprocess
import sys
import tempfile
import unittest

import refresh

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data", "exhibitions.json")
REFRESH_MD = os.path.join(ROOT, "REFRESH.md")

TODAY = datetime.date(2026, 11, 16)


def show(**over):
    base = {
        "title": "A Show",
        "artist": "Someone",
        "venue": "Some Museum",
        "city": "New York",
        "start": "2026-10-01",
        "end": "2027-01-10",
        "tags": ["painting"],
        "blurb": "Blurb.",
        "note": "Note.",
        "url": "https://example.org/show",
    }
    base.update(over)
    return base


def doc(*shows, updated="2026-11-16"):
    return {"updated": updated, "method": "test", "exhibitions": list(shows)}


TARGETS = {"New York": (12, 18), "Amsterdam": (10, 15), "London": (1, 4)}


class FormatTests(unittest.TestCase):
    def test_format_roundtrips_existing_file_byte_for_byte(self):
        with open(DATA, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(refresh.format_json(json.loads(text)), text)


class TargetTests(unittest.TestCase):
    def test_parses_home_region_targets_from_refresh_md(self):
        with open(REFRESH_MD, encoding="utf-8") as f:
            targets = refresh.parse_targets(f.read())
        self.assertEqual(targets["New York"], (12, 18))
        self.assertEqual(targets["Buffalo"], (3, 6))
        self.assertEqual(targets["Washington, DC"], (10, 15))

    def test_parses_international_cities_with_shared_range(self):
        with open(REFRESH_MD, encoding="utf-8") as f:
            targets = refresh.parse_targets(f.read())
        self.assertEqual(targets["Tokyo"], (1, 4))
        self.assertEqual(targets["São Paulo"], (1, 4))


class CheckTests(unittest.TestCase):
    def errors(self, data):
        return refresh.check(data, TODAY, TARGETS)[0]

    def warnings(self, data):
        return refresh.check(data, TODAY, TARGETS)[1]

    def test_clean_document_has_no_errors(self):
        self.assertEqual(self.errors(doc(show())), [])

    def test_flags_closed_show(self):
        errs = self.errors(doc(show(end="2026-11-15")))
        self.assertTrue(any("closed" in e for e in errs), errs)

    def test_flags_start_after_end(self):
        errs = self.errors(doc(show(start="2027-02-01", end="2027-01-10")))
        self.assertTrue(any("start" in e and "end" in e for e in errs), errs)

    def test_flags_malformed_date(self):
        errs = self.errors(doc(show(end="Jan 10 2027")))
        self.assertTrue(any("end" in e for e in errs), errs)

    def test_flags_markup_in_any_field(self):
        errs = self.errors(doc(show(blurb="<b>bold</b>")))
        self.assertTrue(any("markup" in e for e in errs), errs)

    def test_flags_non_https_url(self):
        errs = self.errors(doc(show(url="http://example.org")))
        self.assertTrue(any("url" in e for e in errs), errs)

    def test_flags_unknown_access_value(self):
        errs = self.errors(doc(show(access=["members-only"])))
        self.assertTrue(any("access" in e for e in errs), errs)

    def test_flags_unknown_field(self):
        errs = self.errors(doc(show(verified="2026-11-16")))
        self.assertTrue(any("verified" in e for e in errs), errs)

    def test_flags_missing_field(self):
        s = show()
        del s["note"]
        errs = self.errors(doc(s))
        self.assertTrue(any("note" in e for e in errs), errs)

    def test_flags_duplicate_title_and_venue(self):
        errs = self.errors(doc(show(), show()))
        self.assertTrue(any("duplicate" in e for e in errs), errs)

    def test_flags_updated_not_today(self):
        errs = self.errors(doc(show(), updated="2026-11-02"))
        self.assertTrue(any("updated" in e for e in errs), errs)

    def test_warns_amsterdam_show_without_museumkaart(self):
        warns = self.warnings(doc(show(city="Amsterdam", venue="Rijksmuseum")))
        self.assertTrue(any("museumkaart" in w for w in warns), warns)

    def test_warns_free_venue_without_free_access(self):
        warns = self.warnings(doc(show(city="Washington, DC", venue="Hirshhorn Museum")))
        self.assertTrue(any("free" in w for w in warns), warns)

    def test_warns_city_under_target(self):
        warns = self.warnings(doc(show(city="Amsterdam", venue="Rijksmuseum", access=["museumkaart"])))
        self.assertTrue(any("Amsterdam" in w and "under" in w for w in warns), warns)

    def test_warns_unknown_city(self):
        warns = self.warnings(doc(show(city="Atlantis")))
        self.assertTrue(any("Atlantis" in w for w in warns), warns)


class TriageTests(unittest.TestCase):
    def test_buckets_closed_ending_soon_and_opening_soon(self):
        data = doc(
            show(title="Closed", end="2026-11-15"),
            show(title="Ending", end="2026-12-01"),
            show(title="Opening", start="2026-11-20", end="2027-03-01"),
            show(title="Fine"),
        )
        t = refresh.triage(data, TODAY, TARGETS)
        self.assertEqual([s["title"] for s in t["closed"]], ["Closed"])
        self.assertEqual([s["title"] for s in t["ending_soon"]], ["Ending"])
        self.assertEqual([s["title"] for s in t["opening_soon"]], ["Opening"])

    def test_coverage_counts_exclude_closed_shows(self):
        data = doc(
            show(city="London", end="2026-11-15"),
            show(city="New York"),
        )
        t = refresh.triage(data, TODAY, TARGETS)
        cov = {c["city"]: c for c in t["coverage"]}
        self.assertEqual(cov["London"]["count"], 0)
        self.assertEqual(cov["London"]["target"], (1, 4))
        self.assertTrue(cov["London"]["under"])
        self.assertTrue(cov["New York"]["under"])


class CliTests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-I", os.path.join(HERE, "refresh.py"), *args],
            capture_output=True, text=True,
        )

    def test_check_write_normalizes_formatting_and_exits_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(doc(show()), f, indent=4)
            r = self.run_cli("check", "--write", "--today", "2026-11-16", p)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(p, encoding="utf-8") as f:
                self.assertEqual(f.read(), refresh.format_json(doc(show())))

    def test_check_exits_nonzero_on_errors(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(doc(show(end="2026-01-01")), f)
            r = self.run_cli("check", "--today", "2026-11-16", p)
            self.assertEqual(r.returncode, 1)
            self.assertIn("closed", r.stdout)

    def test_triage_prints_report(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(doc(show(title="Gone", end="2026-01-01")), f)
            r = self.run_cli("triage", "--today", "2026-11-16", p)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Gone", r.stdout)


if __name__ == "__main__":
    unittest.main()

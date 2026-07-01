# The Exhibition Index

A running ledger of the art exhibitions worth crossing a city — or an ocean — to see.
Deep coverage of New York and the DC–Baltimore–Philadelphia corridor, plus the major
international art capitals.

**Live site:** https://tsherif1.github.io/exhibition-index/

## How it works

- [index.html](index.html) — the entire app: a single static page, no build step, no dependencies.
- [data/exhibitions.json](data/exhibitions.json) — the listings, refreshed weekly by a scheduled
  Claude Code routine that researches current shows and verifies every date against museum sources.
- [REFRESH.md](REFRESH.md) — the research rules the routine follows. Policy changes
  (new cities, favorite venues, coverage depth) go here, not in the JSON.

## Running locally

```bash
python3 -m http.server 4173
# then open http://localhost:4173
```

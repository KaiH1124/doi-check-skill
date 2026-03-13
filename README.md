# doi-check-skill

Verify BibTeX references against the [Crossref REST API](https://api.crossref.org) — catch DOI errors, year mismatches, author mismatches, and title discrepancies before manuscript submission.

**Zero dependencies** — pure Python stdlib (`re`, `csv`, `json`, `urllib`, `pathlib`, `argparse`).

---

## Install

```bash
uv tool install "git+https://github.com/KaiH1124/doi-check-skill.git"
doi-check setup
```

The `setup` command auto-detects which AI coding tools you have installed (Claude Code, OpenAI Codex, OpenCode) and copies the appropriate skill/agent config to the right place. After that, your AI assistant will automatically invoke `doi-check` when you ask it to verify references.

Or with pip:

```bash
pip install "git+https://github.com/KaiH1124/doi-check-skill.git"
doi-check setup
```

### What `setup` installs

| Tool | Config file installed |
|------|----------------------|
| Claude Code | `~/.claude/skills/doi-check/SKILL.md` |
| OpenAI Codex / OpenCode | appended to `~/AGENTS.md` |

---

## Usage

```bash
doi-check --bib refs.bib --tex ./manuscript/ --out output/ref_verification/
```

| Flag | Description |
|------|-------------|
| `--bib` | Path to `.bib` file (required) |
| `--tex` | Manuscript root directory containing `.tex` files (required) |
| `--out` | Output directory for CSV and summary (default: `output/ref_verification`) |
| `--no-interactive` | Skip interactive repair — report only |

---

## What it does

### 5-step workflow

1. **Filter to cited references** — parses `.bib` and scans `.tex` recursively (stripping `%` comments before extracting `\cite{}` keys). Only actually-cited entries are verified.

2. **Verify DOIs via Crossref** — queries `https://api.crossref.org/works/{doi}` for each cited entry with a DOI. Compares year, first-author surname, and title word overlap (≥ 40% required). Writes `ref_check.csv` and `summary.txt`.

3. **Search for correct DOIs** — for FLAGGED / ERROR entries, searches Crossref by title + author and presents the top-5 candidates.

4. **Update `.bib`** — two repair modes:
   - `doi-only`: replace only the `doi` field
   - `full`: fetch complete metadata from Crossref and regenerate the entire entry

5. **Loop until clean** — repeats until zero FLAGGED / ERROR entries remain.

---

## Output

### `ref_check.csv` columns

| Column | Description |
|--------|-------------|
| `cite_key` | BibTeX citation key |
| `status` | `OK` / `FLAGGED` / `ERROR` / `SKIP_NO_DOI` |
| `mismatch_flags` | Pipe-separated list of detected mismatches |
| `bib_doi` | DOI as recorded in `.bib` |
| `link` | `https://doi.org/<doi>` |
| `bib_year` / `cr_year` | Year in `.bib` vs Crossref |
| `bib_first_author` / `cr_first_author` | First author in `.bib` vs Crossref |
| `bib_title` / `cr_title` | Title (first 100 chars) in `.bib` vs Crossref |

### Status values

| Status | Meaning |
|--------|---------|
| `OK` | DOI resolved; year, author, title all match |
| `FLAGGED` | DOI resolved but at least one mismatch detected |
| `ERROR` | Crossref could not resolve the DOI (404, network, etc.) |
| `SKIP_NO_DOI` | Entry has no DOI (books, standards, theses) — not queried |

### Mismatch flags

- `YEAR_MISMATCH(bib=XXXX,cr=YYYY)` — year differs
- `AUTHOR_MISMATCH(bib=surname,cr=surname)` — first-author surname differs
- `TITLE_LOW_OVERLAP(0.XX)` — fewer than 40% of significant words match
- `API_ERROR: ...` — network or HTTP error

---

## Notes

- Crossref rate limit: 0.2 s sleep between requests — ~15 s for 50 DOIs
- `TITLE_LOW_OVERLAP` alone may be a false positive for old papers where Crossref metadata is incomplete
- Books, standards (ISO/ASHRAE), PhD theses, GitHub repos have no DOI → `SKIP_NO_DOI`
- **Never add inline BibTeX comments** (`doi = {10.x/y},  % note`): BibTeX treats them as field names and silently drops the entire entry. Use standalone `%` comment lines before entries instead.

---

## Claude Code Skill

This tool ships with a `SKILL.md` that registers it as a Claude Code skill. Once installed, Claude will automatically invoke `doi-check` when you ask to "check my references", "verify DOIs", "validate citations", or similar.

---

## License

MIT — see [LICENSE](LICENSE).

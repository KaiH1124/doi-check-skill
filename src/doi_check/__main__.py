"""
doi_check  —  Main orchestrator for the doi-check workflow
----------------------------------------------------------
Usage:
  doi-check --bib <path>.bib --tex <manuscript_dir> [--out <dir>]
            [--no-interactive]

Workflow
--------
1. Parse .bib + scan .tex  →  cited keys only
2. Verify every cited DOI via Crossref  →  CSV + summary.txt
3. (interactive) For each FLAGGED / ERROR entry:
     a. Search Crossref by title + author
     b. Present candidates, ask user to confirm correct DOI
     c. Patch .bib (doi only, or full metadata)
4. Ask user whether to re-run the check
5. Loop until clean, then prompt user to double-check manually

All network calls use Python stdlib only (no pip installs needed).
"""

import re
import csv
import sys
import time
import argparse
from pathlib import Path

from doi_check.bib_utils    import parse_bib, collect_cited_keys
from doi_check.crossref_api import query_doi, extract_fields, detect_mismatches, search_by_title_author
from doi_check.bib_updater  import fetch_metadata, format_bibtex_entry, patch_bib_entry


# ── CSV schema ────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "cite_key", "entry_type", "status", "mismatch_flags",
    "bib_doi", "link", "bib_year", "bib_first_author", "bib_title",
    "cr_title", "cr_first_author", "cr_year", "cr_journal", "cr_error",
]


# ── Step 1 + 2: verify all cited DOIs ────────────────────────────────────────

def run_check(bib_path: Path, tex_dir: Path, out_dir: Path) -> tuple:
    """
    Parse bib, collect cited keys, verify DOIs against Crossref.

    Returns (rows, bib_entries, cited_in_bib, missing_in_bib).
    rows is a list of dicts with CSV_FIELDS keys.
    """
    print(f"\n── [1/2] Parsing {bib_path.name} …")
    bib_entries = parse_bib(bib_path)
    print(f"   Total entries in .bib : {len(bib_entries)}")

    print(f"── [2/2] Scanning {tex_dir.name}/ for \\cite{{}} …")
    cited_keys = collect_cited_keys(tex_dir)
    print(f"   Unique cite-keys found : {len(cited_keys)}")

    cited_in_bib   = cited_keys & set(bib_entries)
    missing_in_bib = cited_keys - set(bib_entries)
    print(f"   Cited & in bib         : {len(cited_in_bib)}")
    if missing_in_bib:
        print(f"   ⚠  Cited but NOT in bib: {sorted(missing_in_bib)}")

    has_doi = {k for k in cited_in_bib if bib_entries[k]["doi"]}
    no_doi  = {k for k in cited_in_bib if not bib_entries[k]["doi"]}
    print(f"   With DOI (to verify)   : {len(has_doi)}")
    print(f"   Without DOI (skipped)  : {len(no_doi)}")

    print(f"\n── Verifying {len(has_doi)} DOIs via Crossref …")
    rows = []
    for idx, key in enumerate(sorted(has_doi), 1):
        entry = bib_entries[key]
        doi   = entry["doi"]
        print(f"   [{idx:>3}/{len(has_doi)}] {key}  →  {doi}")

        msg  = query_doi(doi)
        cr   = extract_fields(msg)
        flags = detect_mismatches(entry, cr)

        first_author_bib = ""
        if entry["authors"]:
            raw = re.split(r"\band\b", entry["authors"], flags=re.IGNORECASE)[0].strip()
            first_author_bib = raw.split(",")[0].strip() if "," in raw else raw.split()[-1].strip()

        rows.append({
            "cite_key":        key,
            "entry_type":      entry["type"],
            "bib_doi":         doi,
            "link":            f"https://doi.org/{doi}",
            "bib_year":        entry["year"],
            "bib_first_author": first_author_bib,
            "bib_title":       entry["title"][:100],
            "cr_title":        cr.get("cr_title", "")[:100],
            "cr_first_author": cr.get("cr_first_author", ""),
            "cr_year":         cr.get("cr_year", ""),
            "cr_journal":      cr.get("cr_journal", ""),
            "cr_error":        cr.get("cr_error", ""),
            "status": ("ERROR"   if cr.get("cr_error") else
                       "FLAGGED" if flags else "OK"),
            "mismatch_flags": " | ".join(flags),
        })
        time.sleep(0.2)

    # No-DOI entries
    for key in sorted(no_doi):
        entry = bib_entries[key]
        rows.append({
            "cite_key": key, "entry_type": entry["type"],
            "bib_doi": "", "link": "",
            "bib_year": entry["year"], "bib_first_author": "",
            "bib_title": entry["title"][:100],
            "cr_title": "", "cr_first_author": "", "cr_year": "",
            "cr_journal": "", "cr_error": "",
            "status": "SKIP_NO_DOI", "mismatch_flags": "",
        })

    return rows, bib_entries, cited_in_bib, missing_in_bib


# ── Write outputs ─────────────────────────────────────────────────────────────

def write_outputs(rows: list, bib_path: Path, tex_dir: Path,
                  cited_in_bib: set, missing_in_bib: set,
                  out_dir: Path) -> Path:
    """Write CSV and summary.txt; return csv path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "ref_check.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    ok_rows      = [r for r in rows if r["status"] == "OK"]
    flagged_rows = [r for r in rows if r["status"] == "FLAGGED"]
    error_rows   = [r for r in rows if r["status"] == "ERROR"]
    skip_rows    = [r for r in rows if r["status"] == "SKIP_NO_DOI"]

    lines = [
        "═" * 62,
        "  Reference DOI Verification Report",
        "═" * 62,
        f"  .bib file            : {bib_path}",
        f"  Manuscript dir       : {tex_dir}",
        "",
        f"  Unique \\cite keys in .tex         : {len(cited_in_bib) + len(missing_in_bib)}",
        f"    └─ found in bib                 : {len(cited_in_bib)}",
        f"    └─ MISSING from bib             : {len(missing_in_bib)}",
        "",
        f"  Cited with DOI (Crossref checked) : {len(ok_rows)+len(flagged_rows)+len(error_rows)}",
        f"    └─ OK                           : {len(ok_rows)}",
        f"    └─ FLAGGED (mismatch)           : {len(flagged_rows)}",
        f"    └─ ERROR (DOI/API failure)      : {len(error_rows)}",
        f"  Cited without DOI (skipped)       : {len(skip_rows)}",
        "",
    ]

    if missing_in_bib:
        lines += ["── CITED BUT MISSING FROM BIB ──────────────────────────"]
        lines += [f"  {k}" for k in sorted(missing_in_bib)]
        lines += [""]

    if flagged_rows:
        lines += ["── FLAGGED ENTRIES ─────────────────────────────────────"]
        for r in flagged_rows:
            lines += [
                f"  {r['cite_key']}",
                f"    DOI   : {r['bib_doi']}",
                f"    Link  : {r['link']}",
                f"    Flags : {r['mismatch_flags']}",
                f"    BIB   : {r['bib_title'][:72]}",
                f"    CR    : {r['cr_title'][:72]}",
                "",
            ]

    if error_rows:
        lines += ["── API / DOI ERRORS ────────────────────────────────────"]
        for r in error_rows:
            lines += [f"  {r['cite_key']}  ({r['bib_doi']})",
                      f"    → {r['cr_error']}"]
        lines += [""]

    if skip_rows:
        lines += ["── SKIPPED (no DOI — books/standards/theses) ───────────"]
        lines += [f"  {r['cite_key']}  [{r['entry_type']}]" for r in skip_rows]
        lines += [""]

    lines += [f"  CSV  → {csv_path}",
              f"  TXT  → {out_dir / 'summary.txt'}"]

    report = "\n".join(lines)
    (out_dir / "summary.txt").write_text(report, encoding="utf-8")
    print("\n" + report)
    return csv_path


# ── Step 3: interactive fix loop ──────────────────────────────────────────────

def _ask(prompt: str, choices: list) -> str:
    choices_str = "/".join(choices)
    while True:
        ans = input(f"{prompt} [{choices_str}]: ").strip().lower()
        if ans in [c.lower() for c in choices]:
            return ans
        print(f"  Please enter one of: {choices_str}")


def fix_flagged_entries(rows: list, bib_entries: dict,
                        bib_path: Path) -> bool:
    """
    Interactively fix FLAGGED and ERROR entries.

    Returns True if any changes were made to the .bib file.
    """
    problem_rows = [r for r in rows if r["status"] in ("FLAGGED", "ERROR")]
    if not problem_rows:
        return False

    print(f"\n── Found {len(problem_rows)} entries to fix.")
    changed = False

    for r in problem_rows:
        key   = r["cite_key"]
        entry = bib_entries[key]
        print(f"\n{'─'*60}")
        print(f"  Key    : {key}")
        print(f"  Status : {r['status']}  {r['mismatch_flags']}")
        print(f"  BIB    : {r['bib_title']}")
        print(f"  CR     : {r['cr_title'] or '(no Crossref hit)'}")
        print(f"  DOI    : {r['bib_doi']}  →  {r['link']}")

        action = _ask("  Fix this entry?", ["y", "n", "skip"])
        if action in ("n", "skip"):
            continue

        # Search Crossref for candidates
        print(f"\n  Searching Crossref: \"{entry['title'][:60]}\" + {entry['authors'][:30]} …")
        first_author = ""
        if entry["authors"]:
            raw = re.split(r"\band\b", entry["authors"], flags=re.IGNORECASE)[0].strip()
            first_author = raw.split(",")[0].strip() if "," in raw else raw.split()[-1].strip()

        candidates = search_by_title_author(
            title=entry["title"], first_author=first_author, year=entry["year"]
        )

        if not candidates:
            print("  No candidates found. Skipping.")
            continue

        print(f"\n  Top {len(candidates)} Crossref results:")
        for i, c in enumerate(candidates, 1):
            print(f"  [{i}] {c['first_author']} ({c['year']})  {c['journal']}")
            print(f"      {c['title'][:72]}")
            print(f"      DOI: {c['doi']}  →  {c['link']}")

        choice = input(
            f"\n  Enter number to use [1-{len(candidates)}], "
            f"'m' to enter DOI manually, or 's' to skip: "
        ).strip().lower()

        new_doi = None
        if choice == "s":
            continue
        elif choice == "m":
            new_doi = input("  Enter correct DOI: ").strip()
        elif choice.isdigit() and 1 <= int(choice) <= len(candidates):
            new_doi = candidates[int(choice) - 1]["doi"]
        else:
            print("  Invalid input. Skipping.")
            continue

        if not new_doi:
            continue

        update_all = _ask(
            f"  Update ONLY the doi field, or fetch and replace ALL metadata from Crossref?",
            ["doi-only", "full"]
        )

        ok = patch_bib_entry(
            bib_path, key, new_doi,
            update_fields=(update_all == "full")
        )
        if ok:
            changed = True

    return changed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Verify cited BibTeX DOIs via Crossref, with interactive repair.",
    )
    parser.add_argument("--bib", required=True, help="Path to .bib file")
    parser.add_argument("--tex", required=True,
                        help="Manuscript root directory (contains .tex files)")
    parser.add_argument("--out", default="output/ref_verification",
                        help="Output directory (default: output/ref_verification)")
    parser.add_argument("--no-interactive", action="store_true",
                        help="Skip the interactive repair step (report only)")
    args = parser.parse_args()

    bib = args.bib
    tex = args.tex

    bib_path = Path(args.bib).expanduser().resolve()
    tex_dir  = Path(args.tex).expanduser().resolve()
    out_dir  = Path(args.out).expanduser()

    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'═'*62}")
        print(f"  doi-check  —  iteration {iteration}")
        print(f"{'═'*62}")

        rows, bib_entries, cited_in_bib, missing_in_bib = run_check(
            bib_path, tex_dir, out_dir
        )
        csv_path = write_outputs(
            rows, bib_path, tex_dir, cited_in_bib, missing_in_bib, out_dir
        )

        flagged = [r for r in rows if r["status"] == "FLAGGED"]
        errors  = [r for r in rows if r["status"] == "ERROR"]
        n_problems = len(flagged) + len(errors)

        if n_problems == 0:
            print("\n✓ All cited DOIs verified — no mismatches detected.")
            print("  Please do a final manual review of the CSV before submission:")
            print(f"  {csv_path}")
            break

        if args.no_interactive:
            print(f"\n  {n_problems} issue(s) found. See CSV for details.")
            break

        ans = _ask(
            f"\n  {n_problems} issue(s) found. Start interactive repair now?",
            ["y", "n"]
        )
        if ans == "n":
            print(f"  Skipping repair. See CSV: {csv_path}")
            break

        changed = fix_flagged_entries(rows, bib_entries, bib_path)

        if not changed:
            print("\n  No changes made.")
            break

        ans = _ask("\n  Changes saved. Re-run the check to verify?", ["y", "n"])
        if ans == "n":
            print(f"  Done. Final manual review recommended: {csv_path}")
            break
        # loop back for re-check


if __name__ == "__main__":
    main()

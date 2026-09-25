"""Extract evaluation rows from librarian-authored MARC (.mrc) files.

The output mirrors the ISBN test-set shape used by collect_testset.py while
keeping enough MARC-derived metadata for field-by-field evaluation.

Usage:
  python ai/evaluation/extract_marc_gold_set.py --source-dir "C:/.../TalkFile_마크"
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - script execution from repository root
    from ai.evaluation.evaluate_koma import FieldOccurrence, RecordData, parse_gold_records
except ModuleNotFoundError:  # pragma: no cover
    from evaluate_koma import FieldOccurrence, RecordData, parse_gold_records


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = Path.home() / "Downloads" / "TalkFile_마크"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "ai" / "evaluation" / "data" / "testsets"

TRANSLATION_RE = re.compile(r"(옮김|번역|역주|역자|옮긴이|원작|원저|translat)", re.IGNORECASE)
MULTI_AUTHOR_RE = re.compile(r"(;|,|·|ㆍ|/| 외\b|공저|공동|엮음|편저|글\s*;|그림\s*;)")
ASCII_RE = re.compile(r"[A-Za-z]{3,}")
YEAR_RE = re.compile(r"\d{4}")


@dataclass
class MarcBookRow:
    id: str
    isbn: str
    category: str
    reference_available: str
    marc_available: str
    kdc_group: str
    validation_tier: str
    title: str
    author: str
    publisher: str
    publish_year: str
    kdc: str
    ddc: str
    language_code: str
    field_tags: str
    source_mrc_file: str


def subfield_values(record: RecordData, tag: str, code: str) -> list[str]:
    values: list[str] = []
    for occurrence in record.tags.get(tag, []):
        values.extend(value.strip() for subfield_code, value in occurrence.subfields if subfield_code == code and value.strip())
    return values


def first_subfield(record: RecordData, tag: str, *codes: str) -> str:
    for code in codes:
        values = subfield_values(record, tag, code)
        if values:
            return values[0]
    return ""


def all_subfield_text(record: RecordData, tags: Iterable[str]) -> str:
    parts: list[str] = []
    for tag in tags:
        for occurrence in record.tags.get(tag, []):
            parts.extend(value for _, value in occurrence.subfields)
    return " ".join(parts)


def strip_trailing_punctuation(value: str) -> str:
    return value.strip().strip(" /:;,.=")


def extract_title(record: RecordData) -> str:
    title = strip_trailing_punctuation(first_subfield(record, "245", "a"))
    subtitle = strip_trailing_punctuation(first_subfield(record, "245", "b"))
    if subtitle:
        return strip_trailing_punctuation(f"{title}: {subtitle}")
    return title


def extract_author(record: RecordData) -> str:
    authors: list[str] = []
    for tag in ("100", "110", "111", "700", "710", "711"):
        authors.extend(subfield_values(record, tag, "a"))
    if authors:
        return " ; ".join(strip_trailing_punctuation(author) for author in authors)
    statement = first_subfield(record, "245", "c")
    return strip_trailing_punctuation(statement)


def extract_publisher(record: RecordData) -> str:
    value = first_subfield(record, "260", "b") or first_subfield(record, "264", "b")
    return strip_trailing_punctuation(value)


def extract_year(record: RecordData) -> str:
    value = first_subfield(record, "260", "c") or first_subfield(record, "264", "c")
    match = YEAR_RE.search(value)
    return match.group(0) if match else strip_trailing_punctuation(value)


def extract_kdc(record: RecordData) -> str:
    return strip_trailing_punctuation(first_subfield(record, "056", "a"))


def extract_ddc(record: RecordData) -> str:
    return strip_trailing_punctuation(first_subfield(record, "082", "a"))


def extract_language(record: RecordData) -> str:
    return strip_trailing_punctuation(first_subfield(record, "041", "a"))


def kdc_group(kdc: str) -> str:
    match = re.search(r"\d", kdc or "")
    return match.group(0) if match else ""


def has_multiple_authors(record: RecordData, author_text: str) -> bool:
    contributor_count = sum(len(record.tags.get(tag, [])) for tag in ("100", "110", "111", "700", "710", "711"))
    if contributor_count >= 2:
        return True
    responsibility = first_subfield(record, "245", "c")
    return bool(MULTI_AUTHOR_RE.search(" ".join([author_text, responsibility])))


def classify_category(record: RecordData, *, title: str, author: str, publisher: str, language_code: str) -> str:
    evidence_text = all_subfield_text(record, ("041", "240", "245", "246", "500", "507", "534", "700"))
    if TRANSLATION_RE.search(evidence_text):
        return "번역서"
    if language_code and language_code.lower() not in {"kor", "ko"}:
        return "외국도서"
    if ASCII_RE.search(title) and ASCII_RE.search(publisher):
        return "외국도서"
    if has_multiple_authors(record, author):
        return "복수저자"
    return "일반도서"


def field_tags(record: RecordData) -> str:
    return ",".join(sorted(record.tags.keys()))


def build_rows(source_dir: Path) -> list[MarcBookRow]:
    rows: list[MarcBookRow] = []

    for path in sorted(source_dir.glob("*.mrc")):
        records = parse_gold_records(path)
        for record in records:
            title = extract_title(record)
            author = extract_author(record)
            publisher = extract_publisher(record)
            publish_year = extract_year(record)
            kdc = extract_kdc(record)
            ddc = extract_ddc(record)
            language_code = extract_language(record)
            category = classify_category(
                record,
                title=title,
                author=author,
                publisher=publisher,
                language_code=language_code,
            )
            rows.append(
                MarcBookRow(
                    id=f"MARC-{len(rows) + 1:04d}",
                    isbn=record.isbn,
                    category=category,
                    reference_available="true",
                    marc_available="true",
                    kdc_group=kdc_group(kdc),
                    validation_tier="gold_marc",
                    title=title,
                    author=author,
                    publisher=publisher,
                    publish_year=publish_year,
                    kdc=kdc,
                    ddc=ddc,
                    language_code=language_code,
                    field_tags=field_tags(record),
                    source_mrc_file=path.name,
                )
            )

    return rows


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def unique_by_isbn(rows: list[MarcBookRow]) -> list[MarcBookRow]:
    seen: set[str] = set()
    unique_rows: list[MarcBookRow] = []
    for row in rows:
        if row.isbn in seen:
            continue
        seen.add(row.isbn)
        unique_rows.append(row)
    return unique_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract MARC gold evaluation rows from .mrc files.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.source_dir.exists():
        raise SystemExit(f"Source directory does not exist: {args.source_dir}")

    rows = build_rows(args.source_dir)
    unique_rows = unique_by_isbn(rows)
    unique_row_dicts = [row.__dict__ for row in unique_rows]

    full_fields = [
        "id",
        "isbn",
        "category",
        "reference_available",
        "marc_available",
        "kdc_group",
        "validation_tier",
        "title",
        "author",
        "publisher",
        "publish_year",
        "kdc",
        "ddc",
        "language_code",
        "field_tags",
        "source_mrc_file",
    ]
    minimal_fields = ["id", "isbn", "category", "reference_available"]

    write_csv(args.output_dir / "marc_gold_books.csv", unique_row_dicts, full_fields)
    write_csv(args.output_dir / "marc_gold_books_minimal.csv", unique_row_dicts, minimal_fields)

    summary = {
        "source_file_count": len(list(args.source_dir.glob("*.mrc"))),
        "raw_record_count": len(rows),
        "unique_isbn_count": len(unique_rows),
        "duplicate_isbn_count": len(rows) - len(unique_rows),
        "by_category": dict(Counter(row.category for row in unique_rows)),
        "by_kdc_group": dict(sorted(Counter(row.kdc_group or "missing" for row in unique_rows).items())),
        "missing_kdc_count": sum(1 for row in unique_rows if not row.kdc_group),
    }
    (args.output_dir / "marc_gold_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote: {args.output_dir / 'marc_gold_books.csv'}")
    print(f"Wrote: {args.output_dir / 'marc_gold_books_minimal.csv'}")


if __name__ == "__main__":
    main()

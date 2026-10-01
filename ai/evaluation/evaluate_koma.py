from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import request as urllib_request


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_MRC = ROOT_DIR / "docs" / "0428_희망샘도서관4월희망(33)OEM55126-OEM55158.mrc"
DEFAULT_RESULTS_DIR = ROOT_DIR / "eval_results"
DEFAULT_SUMMARY_CSV = ROOT_DIR / "eval_summary.csv"
DEFAULT_SUMMARY_OLD_CSV = ROOT_DIR / "eval_summary_old.csv"
DEFAULT_BOOKS_CSV = ROOT_DIR / "eval_books.csv"
DEFAULT_DETAILS_JSON = ROOT_DIR / "eval_details.json"
DEFAULT_ISBNS_TXT = ROOT_DIR / "eval_isbns.txt"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

RT = b"\x1d"
SF = b"\x1f"
LEADER_LEN = 24
DIRECTORY_ENTRY_LEN = 12

STRUCTURAL_PUNCTUATION_RE = re.compile(r"(^[▼$/\s]+|[\s]*[:;/]+$)")
WHITESPACE_RE = re.compile(r"\s+")
NON_DIGIT_RE = re.compile(r"[^0-9Xx]")
ISBN_CANDIDATE_RE = re.compile(r"[0-9Xx\-\s]{10,20}")
TITLE_COMPARE_RE = re.compile(r"[^0-9A-Za-z가-힣]+")
PAREN_TEXT_RE = re.compile(r"\([^)]*\)")
PUBLISHER_NOISE_RE = re.compile(r"(?:^|\s)(?:주식회사|출판사)(?=\s|$)")
YEAR_RE = re.compile(r"\d{4}")
NUMBER_RE = re.compile(r"\d+")

LANG_SYNONYMS = {
    "fre": "fra",
    "ger": "deu",
    "gre": "ell",
    "rum": "ron",
    "slo": "slk",
    "alb": "sqi",
    "arm": "hye",
    "baq": "eus",
    "bur": "mya",
    "cze": "ces",
    "dut": "nld",
    "ice": "isl",
    "mac": "mkd",
    "mao": "mri",
    "may": "msa",
    "per": "fas",
    "tib": "bod",
    "wel": "cym",
}

STRUCTURED_FIELDS = ["020", "245", "250", "260", "300"]
CLASS_FIELDS = ["056", "082"]
EVALUATED_FIELDS = STRUCTURED_FIELDS + ["041"] + CLASS_FIELDS + ["653"]
STRUCTURED_FIELD_CODES = {
    "245": ("a",),
    "250": ("a",),
    "260": ("b", "c"),
    "300": ("a", "c"),
}


@dataclass
class FieldOccurrence:
    indicator1: str
    indicator2: str
    subfields: list[tuple[str, str]]


@dataclass
class RecordData:
    isbn: str
    tags: dict[str, list[FieldOccurrence]]


def normalize_text(value: str) -> str:
    normalized = STRUCTURAL_PUNCTUATION_RE.sub("", value).strip()
    normalized = normalized.replace("▼", "").strip()
    normalized = normalized.replace('"', "").replace("'", "")
    normalized = WHITESPACE_RE.sub(" ", normalized)
    return normalized.casefold()


def normalize_class_value(value: str) -> str:
    return WHITESPACE_RE.sub("", normalize_text(value))


def normalize_kdc_value(value: str) -> str:
    return normalize_class_value(value).replace(".", "")


def normalize_title_compare_value(value: str) -> str:
    return TITLE_COMPARE_RE.sub("", normalize_text(value))


def normalize_publisher_compare_value(value: str) -> str:
    normalized = normalize_text(value)
    normalized = PAREN_TEXT_RE.sub(" ", normalized)
    normalized = PUBLISHER_NOISE_RE.sub(" ", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized.replace(" ", "")


def normalize_year_compare_value(value: str) -> str:
    match = YEAR_RE.search(value)
    if match is not None:
        return match.group(0)
    return "".join(NUMBER_RE.findall(value))


def normalize_page_compare_value(value: str) -> str:
    numbers = NUMBER_RE.findall(value)
    return numbers[0] if numbers else ""


def normalize_size_compare_value(value: str) -> str:
    numbers = [int(number) for number in NUMBER_RE.findall(value)]
    if not numbers:
        return ""
    if len(numbers) >= 2:
        largest = max(numbers)
        return str(round(largest / 10)) if largest > 100 else str(largest)
    number = numbers[0]
    return str(round(number / 10)) if number > 100 else str(number)


def normalize_lang_code(value: str) -> str:
    code = normalize_text(value)
    return LANG_SYNONYMS.get(code, code)


def is_valid_isbn10(value: str) -> bool:
    if len(value) != 10 or not re.fullmatch(r"\d{9}[\dX]", value):
        return False
    total = sum((10 - index) * (10 if char == "X" else int(char)) for index, char in enumerate(value))
    return total % 11 == 0


def isbn10_to_13(value: str) -> str:
    core = f"978{value[:9]}"
    total = sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(core))
    check_digit = (10 - (total % 10)) % 10
    return f"{core}{check_digit}"


def is_valid_isbn13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    total = sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(value[:12]))
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(value[12])


def extract_normalized_isbns(raw_values: Iterable[str]) -> list[str]:
    normalized_values: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        for candidate in ISBN_CANDIDATE_RE.findall(raw_value):
            compact = NON_DIGIT_RE.sub("", candidate).upper()
            normalized = ""
            if len(compact) == 13 and is_valid_isbn13(compact):
                normalized = compact
            elif len(compact) == 10 and is_valid_isbn10(compact):
                normalized = isbn10_to_13(compact)
            if normalized and normalized not in seen:
                seen.add(normalized)
                normalized_values.append(normalized)
    return normalized_values


def decode_bytes(data: bytes, *, utf8_preferred: bool) -> str:
    encodings = ["utf-8", "cp949", "euc-kr", "latin-1"] if utf8_preferred else ["cp949", "euc-kr", "utf-8", "latin-1"]
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def iter_raw_records(path: Path) -> Iterable[bytes]:
    with path.open("rb") as handle:
        while True:
            first_five = handle.read(5)
            if not first_five:
                break
            if len(first_five) < 5:
                raise ValueError("Truncated MARC leader length")
            record_length = int(first_five)
            chunk = first_five + handle.read(record_length - 5)
            if len(chunk) != record_length or chunk[-1:] != RT:
                raise ValueError("Malformed MARC record framing")
            yield chunk


def parse_raw_record(chunk: bytes) -> tuple[str | None, dict[str, list[FieldOccurrence]]]:
    leader = chunk[:LEADER_LEN]
    utf8_preferred = leader[9:10] == b"a"
    base_address = int(chunk[12:17])
    directory = chunk[LEADER_LEN : base_address - 1]

    tags: dict[str, list[FieldOccurrence]] = defaultdict(list)
    isbn_candidates: list[str] = []

    for index in range(0, len(directory), DIRECTORY_ENTRY_LEN):
        entry = directory[index : index + DIRECTORY_ENTRY_LEN]
        if len(entry) < DIRECTORY_ENTRY_LEN:
            continue
        tag = entry[0:3].decode("ascii")
        field_length = int(entry[3:7])
        offset = int(entry[7:12])
        field_data = chunk[base_address + offset : base_address + offset + field_length - 1]

        if tag < "010":
            continue

        parts = field_data.split(SF)
        indicators_raw = parts[0][:2]
        indicators = decode_bytes(indicators_raw, utf8_preferred=utf8_preferred)
        indicators = (indicators + "  ")[:2]
        subfields: list[tuple[str, str]] = []
        for part in parts[1:]:
            if not part:
                continue
            code = chr(part[0])
            value = decode_bytes(part[1:], utf8_preferred=utf8_preferred)
            subfields.append((code, value))
            if tag == "020" and code == "a":
                isbn_candidates.append(value)

        tags[tag].append(FieldOccurrence(indicator1=indicators[0], indicator2=indicators[1], subfields=subfields))

    normalized_isbns = extract_normalized_isbns(isbn_candidates)
    return (normalized_isbns[0] if normalized_isbns else None), dict(tags)


def parse_marc_with_pymarc(path: Path) -> list[RecordData]:
    try:
        from pymarc import MARCReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("pymarc unavailable") from exc

    records: list[RecordData] = []
    with path.open("rb") as handle:
        reader = MARCReader(handle, to_unicode=True, force_utf8=False, file_encoding="euc-kr", permissive=True)
        for record in reader:
            if record is None:
                continue
            tags: dict[str, list[FieldOccurrence]] = defaultdict(list)
            isbn_candidates: list[str] = []
            for field in record.get_fields():
                if field.is_control_field():
                    continue
                raw_subfields = getattr(field, "subfields", [])
                field_pairs: list[tuple[str, str]] = []
                if raw_subfields and hasattr(raw_subfields[0], "code"):
                    field_pairs = [(item.code, item.value) for item in raw_subfields]
                elif raw_subfields and isinstance(raw_subfields[0], str):
                    field_pairs = list(zip(raw_subfields[0::2], raw_subfields[1::2]))
                tags[field.tag].append(
                    FieldOccurrence(
                        indicator1=getattr(field, "indicator1", " ") or " ",
                        indicator2=getattr(field, "indicator2", " ") or " ",
                        subfields=field_pairs,
                    )
                )
                if field.tag == "020":
                    isbn_candidates.extend(value for code, value in field_pairs if code == "a")

            normalized_isbns = extract_normalized_isbns(isbn_candidates)
            if normalized_isbns:
                records.append(RecordData(isbn=normalized_isbns[0], tags=dict(tags)))
    return records


def parse_gold_records(path: Path) -> list[RecordData]:
    try:
        records = parse_marc_with_pymarc(path)
        if records:
            return records
    except RuntimeError:
        pass

    parsed_records: list[RecordData] = []
    for chunk in iter_raw_records(path):
        isbn, tags = parse_raw_record(chunk)
        if isbn:
            parsed_records.append(RecordData(isbn=isbn, tags=tags))
    return parsed_records


def normalize_occurrence(occurrence: FieldOccurrence) -> FieldOccurrence:
    return FieldOccurrence(
        indicator1=occurrence.indicator1,
        indicator2=occurrence.indicator2,
        subfields=[(code, normalize_text(value)) for code, value in occurrence.subfields],
    )


def normalize_field_map(field_map: dict[str, list[FieldOccurrence]]) -> dict[str, list[FieldOccurrence]]:
    normalized: dict[str, list[FieldOccurrence]] = defaultdict(list)
    for tag, fields in field_map.items():
        for field in fields:
            normalized[tag].append(normalize_occurrence(field))
    return dict(normalized)


def normalize_koma_result(payload: dict[str, Any]) -> tuple[dict[str, list[FieldOccurrence]], set[str]]:
    tags: dict[str, list[FieldOccurrence]] = defaultdict(list)
    for field in payload.get("fields", []):
        tag = field.get("tag")
        subfields = field.get("subfields", [])
        if not isinstance(tag, str) or not isinstance(subfields, list):
            continue
        tags[tag].append(
            FieldOccurrence(
                indicator1=str(field.get("indicator1", " ")) or " ",
                indicator2=str(field.get("indicator2", " ")) or " ",
                subfields=[
                    (str(subfield.get("code", "")), normalize_text(str(subfield.get("value", ""))))
                    for subfield in subfields
                ],
            )
        )
    skipped_tags = {str(item.get("tag")) for item in payload.get("skipped_fields", []) if isinstance(item, dict) and item.get("tag")}
    return dict(tags), skipped_tags


def field_occurrences(field_map: dict[str, list[FieldOccurrence]], tag: str) -> list[FieldOccurrence]:
    return field_map.get(tag, [])


def subfield_values(field_map: dict[str, list[FieldOccurrence]], tag: str, code: str) -> list[str]:
    values: list[str] = []
    for field in field_occurrences(field_map, tag):
        values.extend(value for subfield_code, value in field.subfields if subfield_code == code and value != "")
    return values


def filter_occurrence(occurrence: FieldOccurrence, allowed_codes: tuple[str, ...]) -> FieldOccurrence | None:
    filtered = [(code, value) for code, value in occurrence.subfields if code in allowed_codes and value != ""]
    if not filtered:
        return None
    return FieldOccurrence(indicator1=occurrence.indicator1, indicator2=occurrence.indicator2, subfields=filtered)


def extract_structured_occurrences(field_map: dict[str, list[FieldOccurrence]], tag: str) -> list[FieldOccurrence]:
    allowed_codes = STRUCTURED_FIELD_CODES[tag]
    occurrences: list[FieldOccurrence] = []
    for occurrence in field_occurrences(field_map, tag):
        normalized_subfields = []
        for code, value in occurrence.subfields:
            if code not in allowed_codes:
                continue
            if tag == "245" and code == "a":
                normalized_value = normalize_title_compare_value(value)
            elif tag == "250" and code == "a":
                normalized_value = normalize_text(value)
            elif tag == "260" and code == "b":
                normalized_value = normalize_publisher_compare_value(value)
            elif tag == "260" and code == "c":
                normalized_value = normalize_year_compare_value(value)
            elif tag == "300" and code == "a":
                normalized_value = normalize_page_compare_value(value)
            elif tag == "300" and code == "c":
                normalized_value = normalize_size_compare_value(value)
            else:
                normalized_value = normalize_text(value)
            if normalized_value:
                normalized_subfields.append((code, normalized_value))

        filtered = None
        if normalized_subfields:
            filtered = FieldOccurrence(occurrence.indicator1, occurrence.indicator2, normalized_subfields)
        if filtered is not None:
            occurrences.append(filtered)
    return occurrences


def extract_class_occurrences(field_map: dict[str, list[FieldOccurrence]], tag: str) -> list[FieldOccurrence]:
    occurrences: list[FieldOccurrence] = []
    normalizer = normalize_kdc_value if tag == "056" else normalize_class_value
    for occurrence in field_occurrences(field_map, tag):
        filtered = filter_occurrence(occurrence, ("a",))
        if filtered is not None:
            normalized_subfields = [(code, normalizer(value)) for code, value in filtered.subfields]
            occurrences.append(FieldOccurrence(filtered.indicator1, filtered.indicator2, normalized_subfields))
    return occurrences


def regularity_score(gold_occurrence: FieldOccurrence, koma_occurrence: FieldOccurrence) -> float:
    gold_indicators = (gold_occurrence.indicator1, gold_occurrence.indicator2)
    koma_indicators = (koma_occurrence.indicator1, koma_occurrence.indicator2)
    gold_codes = [code for code, _ in gold_occurrence.subfields]
    koma_codes = [code for code, _ in koma_occurrence.subfields]

    indicators_match = gold_indicators == koma_indicators
    codes_match = gold_codes == koma_codes
    if indicators_match and codes_match:
        return 1.0
    if indicators_match or codes_match:
        return 0.5
    return 0.0


def compare_scalar_field(gold_values: list[str], koma_values: list[str]) -> dict[str, Any]:
    if not gold_values and not koma_values:
        return {"status": "excluded", "score": None}
    if gold_values and not koma_values:
        return {"status": "missing", "score": 0.0}
    if not gold_values and koma_values:
        return {"status": "excluded", "score": None}

    gold_value = gold_values[0]
    koma_value = koma_values[0]
    if gold_value == koma_value:
        return {"status": "exact", "score": 1.0}
    if gold_value in koma_value or koma_value in gold_value:
        return {"status": "partial", "score": 0.5}
    return {"status": "mismatch", "score": 0.0}


def _structured_similarity(tag: str, gold_field: FieldOccurrence, koma_field: FieldOccurrence) -> float:
    gold_map = {code: value for code, value in gold_field.subfields}
    koma_map = {code: value for code, value in koma_field.subfields}
    scores: list[float] = []

    if "a" in gold_map and "a" in koma_map:
        if gold_map["a"] == koma_map["a"]:
            scores.append(1.0)
        elif gold_map["a"] in koma_map["a"] or koma_map["a"] in gold_map["a"]:
            scores.append(0.5)
        else:
            scores.append(0.0)
    elif "a" in gold_map:
        scores.append(0.0)

    if "b" in gold_map and "b" in koma_map:
        if gold_map["b"] == koma_map["b"]:
            scores.append(1.0)
        elif tag == "260" and (gold_map["b"] in koma_map["b"] or koma_map["b"] in gold_map["b"]):
            scores.append(1.0)
        elif gold_map["b"] in koma_map["b"] or koma_map["b"] in gold_map["b"]:
            scores.append(0.5)
        else:
            scores.append(0.0)
    elif "b" in gold_map:
        scores.append(0.0)

    if "c" in gold_map and "c" in koma_map:
        scores.append(1.0 if gold_map["c"] == koma_map["c"] else 0.0)
    elif "c" in gold_map:
        scores.append(0.0)

    if not scores:
        return 0.0
    if all(score == 1.0 for score in scores):
        return 1.0
    if any(score > 0 for score in scores):
        return round(sum(scores) / len(scores), 4)
    return 0.0


def compare_structured_field(tag: str, gold_fields: list[FieldOccurrence], koma_fields: list[FieldOccurrence]) -> dict[str, Any]:
    if not gold_fields and not koma_fields:
        return {"status": "excluded", "score": None, "gold_match": None, "koma_match": None}
    if gold_fields and not koma_fields:
        return {"status": "missing", "score": 0.0, "gold_match": None, "koma_match": None}
    if not gold_fields and koma_fields:
        return {"status": "excluded", "score": None, "gold_match": None, "koma_match": None}

    best_score = -1.0
    best_pair: tuple[FieldOccurrence | None, FieldOccurrence | None] = (None, None)
    for gold_field in gold_fields:
        for koma_field in koma_fields:
            score = _structured_similarity(tag, gold_field, koma_field)
            if score > best_score:
                best_score = score
                best_pair = (gold_field, koma_field)

    if best_score == 1.0:
        status = "exact"
    elif best_score > 0:
        status = "partial"
    else:
        status = "mismatch"
        best_score = 0.0

    return {
        "status": status,
        "score": round(best_score, 4),
        "gold_match": best_pair[0],
        "koma_match": best_pair[1],
    }


def classification_score(gold_value: str, koma_value: str) -> float:
    if gold_value == koma_value:
        return 1.0
    if gold_value.startswith(koma_value) or koma_value.startswith(gold_value):
        return 0.5
    return 0.0


def compare_class_field(gold_values: list[str], koma_values: list[str], *, tag: str) -> dict[str, Any]:
    normalizer = normalize_kdc_value if tag == "056" else normalize_class_value
    gold_values = [normalizer(value) for value in gold_values if normalizer(value)]
    koma_values = [normalizer(value) for value in koma_values if normalizer(value)]
    if not gold_values and not koma_values:
        return {"status": "excluded", "score": None}
    if gold_values and not koma_values:
        return {"status": "missing", "score": 0.0}
    if not gold_values and koma_values:
        return {"status": "excluded", "score": None}

    best = max(classification_score(gold_value, koma_value) for gold_value in gold_values for koma_value in koma_values)
    if best == 1.0:
        return {"status": "exact", "score": 1.0}
    if best > 0:
        return {"status": "partial", "score": best}
    return {"status": "mismatch", "score": 0.0}


def compare_lang_field(gold_values: list[str], koma_values: list[str]) -> dict[str, Any]:
    gold_set = {normalize_lang_code(value) for value in gold_values if value}
    koma_set = {normalize_lang_code(value) for value in koma_values if value}
    if not gold_set and not koma_set:
        return {"status": "excluded", "score": None}
    if gold_set and not koma_set:
        return {"status": "missing", "score": 0.0}
    if not gold_set and koma_set:
        return {"status": "excluded", "score": None}
    if gold_set == koma_set:
        return {"status": "exact", "score": 1.0}

    overlap = gold_set & koma_set
    if overlap:
        return {"status": "partial", "score": len(overlap) / len(gold_set | koma_set)}
    return {"status": "mismatch", "score": 0.0}


def greedy_match_terms(gold_terms: list[str], koma_terms: list[str], *, allow_partial: bool) -> tuple[list[tuple[str, str, str]], list[str], list[str]]:
    remaining_gold = gold_terms.copy()
    matched: list[tuple[str, str, str]] = []
    unmatched_koma: list[str] = []
    for koma_term in koma_terms:
        exact_match = next((gold_term for gold_term in remaining_gold if gold_term == koma_term), None)
        if exact_match is not None:
            matched.append((koma_term, exact_match, "exact"))
            remaining_gold.remove(exact_match)
            continue

        if allow_partial:
            partial_candidates = [gold_term for gold_term in remaining_gold if gold_term in koma_term or koma_term in gold_term]
            if partial_candidates:
                best = max(partial_candidates, key=lambda value: min(len(value), len(koma_term)))
                matched.append((koma_term, best, "partial"))
                remaining_gold.remove(best)
                continue

        unmatched_koma.append(koma_term)

    return matched, remaining_gold, unmatched_koma


def compare_653(gold_field_map: dict[str, list[FieldOccurrence]], koma_field_map: dict[str, list[FieldOccurrence]], *, allow_partial: bool) -> dict[str, Any]:
    gold_terms = sorted({value for tag in ("650", "653") for value in subfield_values(gold_field_map, tag, "a")})
    koma_terms = sorted({value for value in subfield_values(koma_field_map, "653", "a")})

    if not gold_terms:
        return {
            "status": "excluded",
            "precision": None,
            "recall": None,
            "f1": None,
            "matched": [],
            "gold_only": [],
            "koma_only": koma_terms,
        }
    if not koma_terms:
        return {
            "status": "missing",
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "matched": [],
            "gold_only": gold_terms,
            "koma_only": [],
        }

    matched, gold_only, koma_only = greedy_match_terms(gold_terms, koma_terms, allow_partial=allow_partial)
    true_positive = len(matched)
    precision = true_positive / len(koma_terms) if koma_terms else 0.0
    recall = true_positive / len(gold_terms) if gold_terms else 0.0
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    status = "exact" if not gold_only and not koma_only else "partial" if matched else "mismatch"
    return {
        "status": status,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched": [{"koma": koma, "gold": gold, "match_type": match_type} for koma, gold, match_type in matched],
        "gold_only": gold_only,
        "koma_only": koma_only,
    }


def metric_row(
    *,
    tag: str,
    status: str,
    gold_present: bool,
    generated_present: bool,
    score: float | None = None,
    regularity: float | None = None,
    precision: float | None = None,
    recall: float | None = None,
    f1: float | None = None,
    matched: list[dict[str, str]] | None = None,
    gold_only: list[str] | None = None,
    koma_only: list[str] | None = None,
) -> dict[str, Any]:
    excluded = not gold_present
    rich_generated = excluded and generated_present
    accurate = False
    if tag == "653":
        accurate = gold_present and generated_present and status in {"exact", "partial"}
    else:
        accurate = gold_present and generated_present and status == "exact"

    completeness_credit = 1 if gold_present and generated_present else 0
    return {
        "status": "excluded" if excluded else status,
        "gold_present": gold_present,
        "generated_present": generated_present,
        "excluded": excluded,
        "rich_generated": rich_generated,
        "completeness_credit": completeness_credit,
        "accurate": accurate,
        "score": score,
        "regularity": regularity,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched": matched or [],
        "gold_only": gold_only or [],
        "koma_only": koma_only or [],
    }


def compare_record(gold: RecordData, koma_payload: dict[str, Any], *, allow_partial_653: bool) -> dict[str, Any]:
    gold_fields = normalize_field_map(gold.tags)
    koma_fields, skipped_tags = normalize_koma_result(koma_payload)

    field_results: dict[str, Any] = {}
    missing_fields: list[str] = []
    rich_generated_fields: list[str] = []

    gold_020 = extract_normalized_isbns(subfield_values(gold_fields, "020", "a"))
    koma_020 = extract_normalized_isbns(subfield_values(koma_fields, "020", "a"))
    scalar_020 = compare_scalar_field(gold_020, koma_020)
    gold_020_occurrences = field_occurrences(gold_fields, "020")
    koma_020_occurrences = field_occurrences(koma_fields, "020")
    field_results["020"] = metric_row(
        tag="020",
        status=scalar_020["status"],
        gold_present=bool(gold_020),
        generated_present=bool(koma_020),
        score=scalar_020["score"],
        regularity=regularity_score(gold_020_occurrences[0], koma_020_occurrences[0]) if scalar_020["status"] == "exact" and gold_020_occurrences and koma_020_occurrences else None,
    )

    for tag in ("245", "250", "260", "300"):
        gold_occurrences = extract_structured_occurrences(gold_fields, tag)
        koma_occurrences = extract_structured_occurrences(koma_fields, tag)
        structured_result = compare_structured_field(tag, gold_occurrences, koma_occurrences)
        field_results[tag] = metric_row(
            tag=tag,
            status=structured_result["status"],
            gold_present=bool(gold_occurrences),
            generated_present=bool(koma_occurrences),
            score=structured_result["score"],
            regularity=regularity_score(structured_result["gold_match"], structured_result["koma_match"]) if structured_result["status"] == "exact" and structured_result["gold_match"] and structured_result["koma_match"] else None,
        )

    gold_041 = subfield_values(gold_fields, "041", "a")
    koma_041 = subfield_values(koma_fields, "041", "a")
    lang_result = compare_lang_field(gold_041, koma_041)
    gold_041_occurrences = field_occurrences(gold_fields, "041")
    koma_041_occurrences = field_occurrences(koma_fields, "041")
    field_results["041"] = metric_row(
        tag="041",
        status=lang_result["status"],
        gold_present=bool(gold_041),
        generated_present=bool(koma_041),
        score=lang_result["score"],
        regularity=regularity_score(gold_041_occurrences[0], koma_041_occurrences[0]) if lang_result["status"] == "exact" and gold_041_occurrences and koma_041_occurrences else None,
    )

    for tag in ("056", "082"):
        gold_values = subfield_values(gold_fields, tag, "a")
        koma_values = subfield_values(koma_fields, tag, "a")
        class_result = compare_class_field(gold_values, koma_values, tag=tag)
        gold_occurrences = extract_class_occurrences(gold_fields, tag)
        koma_occurrences = extract_class_occurrences(koma_fields, tag)
        field_results[tag] = metric_row(
            tag=tag,
            status=class_result["status"],
            gold_present=bool(gold_values),
            generated_present=bool(koma_values),
            score=class_result["score"],
            regularity=regularity_score(gold_occurrences[0], koma_occurrences[0]) if class_result["status"] == "exact" and gold_occurrences and koma_occurrences else None,
        )

    compare_653_result = compare_653(gold_fields, koma_fields, allow_partial=allow_partial_653)
    gold_653_terms = sorted({value for tag in ("650", "653") for value in subfield_values(gold_fields, tag, "a")})
    koma_653_terms = sorted({value for value in subfield_values(koma_fields, "653", "a")})
    field_results["653"] = metric_row(
        tag="653",
        status=compare_653_result["status"],
        gold_present=bool(gold_653_terms),
        generated_present=bool(koma_653_terms),
        precision=compare_653_result["precision"],
        recall=compare_653_result["recall"],
        f1=compare_653_result["f1"],
        matched=compare_653_result["matched"],
        gold_only=compare_653_result["gold_only"],
        koma_only=compare_653_result["koma_only"],
    )

    for tag in EVALUATED_FIELDS:
        result = field_results[tag]
        if result["gold_present"] and not result["generated_present"]:
            missing_fields.append(tag)
        if result["rich_generated"]:
            rich_generated_fields.append(tag)

    return {
        "isbn": gold.isbn,
        "field_results": field_results,
        "missing_fields": missing_fields,
        "rich_generated_fields": rich_generated_fields,
        "skipped_tags": sorted(skipped_tags),
    }


def safe_average(values: list[float]) -> float | str:
    return round(sum(values) / len(values), 4) if values else ""


def to_percent(value: float | str) -> float | str:
    return round(value * 100, 2) if isinstance(value, float) else ""


def build_summary_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tag in EVALUATED_FIELDS:
        gold_count = generated_count = accurate_count = 0
        exact = partial = mismatch = missing = 0
        excluded_count = rich_generated_count = 0
        regularities: list[float] = []
        precisions: list[float] = []
        recalls: list[float] = []
        f1s: list[float] = []

        for result in results:
            field_result = result["field_results"][tag]
            if field_result["excluded"]:
                excluded_count += 1
                if field_result["rich_generated"]:
                    rich_generated_count += 1
                continue

            gold_count += 1
            status = field_result["status"]
            if field_result["generated_present"]:
                generated_count += 1
            if field_result["accurate"]:
                accurate_count += 1
            if field_result["regularity"] is not None:
                regularities.append(field_result["regularity"])

            if status == "exact":
                exact += 1
            elif status == "partial":
                partial += 1
            elif status == "mismatch":
                mismatch += 1
            elif status == "missing":
                missing += 1

            if tag == "653" and field_result["precision"] is not None:
                precisions.append(field_result["precision"])
                recalls.append(field_result["recall"])
                f1s.append(field_result["f1"])

        completeness = round(generated_count / gold_count, 4) if gold_count else ""
        accuracy = round(accurate_count / generated_count, 4) if generated_count else ""
        regularity = safe_average(regularities)

        rows.append(
            {
                "field": tag,
                "gold_count": gold_count,
                "generated_count": generated_count,
                "accurate_count": accurate_count,
                "completeness": completeness,
                "accuracy": accuracy,
                "regularity": regularity,
                "completeness_100": to_percent(completeness),
                "accuracy_100": to_percent(accuracy),
                "regularity_100": to_percent(regularity),
                "excluded_count": excluded_count,
                "rich_generated_count": rich_generated_count,
                "exact_count": exact,
                "partial_count": partial,
                "mismatch_count": mismatch,
                "missing_count": missing,
                "avg_precision": safe_average(precisions) if tag == "653" else "",
                "avg_recall": safe_average(recalls) if tag == "653" else "",
                "avg_f1": safe_average(f1s) if tag == "653" else "",
            }
        )

    metric_fields = [row for row in rows if row["field"] != "653"]
    all_fields = rows
    overall = {
        "field": "OVERALL",
        "gold_count": "",
        "generated_count": "",
        "accurate_count": "",
        "completeness": safe_average([row["completeness"] for row in all_fields if row["completeness"] != ""]),
        "accuracy": safe_average([row["accuracy"] for row in all_fields if row["accuracy"] != ""]),
        "regularity": safe_average([row["regularity"] for row in metric_fields if row["regularity"] != ""]),
        "completeness_100": "",
        "accuracy_100": "",
        "regularity_100": "",
        "excluded_count": sum(int(row["excluded_count"]) for row in rows),
        "rich_generated_count": sum(int(row["rich_generated_count"]) for row in rows),
        "exact_count": "",
        "partial_count": "",
        "mismatch_count": "",
        "missing_count": "",
        "avg_precision": safe_average([row["avg_precision"] for row in rows if row["avg_precision"] != ""]),
        "avg_recall": safe_average([row["avg_recall"] for row in rows if row["avg_recall"] != ""]),
        "avg_f1": safe_average([row["avg_f1"] for row in rows if row["avg_f1"] != ""]),
    }
    overall["completeness_100"] = to_percent(overall["completeness"])
    overall["accuracy_100"] = to_percent(overall["accuracy"])
    overall["regularity_100"] = to_percent(overall["regularity"])
    rows.append(overall)
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_book_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        row: dict[str, Any] = {
            "isbn": result["isbn"],
            "missing_fields": ",".join(result["missing_fields"]),
            "rich_generated_fields": ",".join(result["rich_generated_fields"]),
            "skipped_tags": ",".join(result["skipped_tags"]),
        }
        for tag in STRUCTURED_FIELDS + ["041", "056", "082"]:
            row[f"{tag}_status"] = result["field_results"][tag]["status"]
            row[f"{tag}_completeness"] = result["field_results"][tag]["completeness_credit"]
            row[f"{tag}_accurate"] = result["field_results"][tag]["accurate"]
            row[f"{tag}_regularity"] = result["field_results"][tag]["regularity"]
        row["653_status"] = result["field_results"]["653"]["status"]
        row["653_precision"] = result["field_results"]["653"]["precision"]
        row["653_recall"] = result["field_results"]["653"]["recall"]
        row["653_f1"] = result["field_results"]["653"]["f1"]
        rows.append(row)
    return rows


def backup_summary(path: Path, backup_path: Path) -> None:
    if path.exists():
        shutil.copyfile(path, backup_path)


def save_isbn_list(isbns: list[str], path: Path) -> None:
    path.write_text("\n".join(isbns) + "\n", encoding="utf-8")


def ensure_results_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def generate_result_for_isbn(base_url: str, isbn: str) -> tuple[int, dict[str, Any]]:
    payload = json.dumps({"isbn": isbn}, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        f"{base_url.rstrip('/')}/api/generate/marc",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=180) as response:
            body = response.read().decode("utf-8")
            return response.getcode(), json.loads(body)
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"detail": body}
        return exc.code, parsed


def collect_koma_outputs(
    isbns: list[str],
    *,
    base_url: str,
    results_dir: Path,
    sleep_seconds: float,
    force_regenerate: bool,
) -> None:
    ensure_results_dir(results_dir)
    for isbn in isbns:
        target_path = results_dir / f"{isbn}.json"
        error_path = results_dir / f"{isbn}.error.json"
        if target_path.exists() and not force_regenerate:
            continue

        status_code, payload = generate_result_for_isbn(base_url, isbn)
        if status_code == 200:
            target_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            if error_path.exists():
                error_path.unlink()
        else:
            error_payload = {"isbn": isbn, "status_code": status_code, "payload": payload}
            error_path.write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(sleep_seconds)


def load_koma_results(results_dir: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not results_dir.exists():
        return results
    for path in sorted(results_dir.glob("*.json")):
        if path.name.endswith(".error.json"):
            continue
        try:
            results[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate KOMA GenerateResult JSON against gold MARC .mrc records.")
    parser.add_argument("--gold-mrc", type=Path, default=DEFAULT_GOLD_MRC)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--summary-old-csv", type=Path, default=DEFAULT_SUMMARY_OLD_CSV)
    parser.add_argument("--books-csv", type=Path, default=DEFAULT_BOOKS_CSV)
    parser.add_argument("--details-json", type=Path, default=DEFAULT_DETAILS_JSON)
    parser.add_argument("--isbns-txt", type=Path, default=DEFAULT_ISBNS_TXT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--skip-generate", action="store_true")
    parser.add_argument("--force-regenerate", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-partial-653", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gold_records = parse_gold_records(args.gold_mrc)
    if not gold_records:
        raise SystemExit(f"No MARC records parsed from {args.gold_mrc}")
    if args.limit is not None:
        gold_records = gold_records[: args.limit]

    isbns = [record.isbn for record in gold_records]
    save_isbn_list(isbns, args.isbns_txt)

    print(f"Gold MARC: {args.gold_mrc}")
    print(f"Parsed records: {len(gold_records)}")
    print("ISBN list:")
    for isbn in isbns:
        print(f"- {isbn}")

    if not args.skip_generate:
        collect_koma_outputs(
            isbns,
            base_url=args.base_url,
            results_dir=args.results_dir,
            sleep_seconds=args.sleep_seconds,
            force_regenerate=args.force_regenerate,
        )

    koma_results = load_koma_results(args.results_dir)
    available_isbns = [isbn for isbn in isbns if isbn in koma_results]
    missing_outputs = [isbn for isbn in isbns if isbn not in koma_results]
    compared_results = [
        compare_record(record, koma_results[record.isbn], allow_partial_653=not args.no_partial_653)
        for record in gold_records
        if record.isbn in koma_results
    ]

    summary_rows = build_summary_rows(compared_results)
    book_rows = build_book_rows(compared_results)
    backup_summary(args.summary_csv, args.summary_old_csv)
    write_csv(args.summary_csv, summary_rows)
    write_csv(args.books_csv, book_rows)

    args.details_json.write_text(
        json.dumps(
            {
                "gold_mrc": str(args.gold_mrc),
                "gold_record_count": len(gold_records),
                "available_result_count": len(available_isbns),
                "missing_result_count": len(missing_outputs),
                "missing_results": missing_outputs,
                "summary": summary_rows,
                "books": compared_results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(f"Available KOMA outputs: {len(available_isbns)} / {len(isbns)}")
    if missing_outputs:
        print("Missing outputs:")
        for isbn in missing_outputs:
            print(f"- {isbn}")

    print(f"Summary CSV: {args.summary_csv}")
    print(f"Summary backup: {args.summary_old_csv}")
    print(f"Books CSV:   {args.books_csv}")
    print(f"Details JSON:{args.details_json}")

    print()
    print("Field summary:")
    for row in summary_rows:
        if row["field"] == "OVERALL":
            print(
                f"- OVERALL: completeness={row['completeness']} accuracy={row['accuracy']} regularity={row['regularity']} "
                f"P={row['avg_precision']} R={row['avg_recall']} F1={row['avg_f1']}"
            )
            continue

        if row["field"] == "653":
            print(
                f"- {row['field']}: gold={row['gold_count']} generated={row['generated_count']} accurate={row['accurate_count']} "
                f"completeness={row['completeness']} accuracy={row['accuracy']} excluded={row['excluded_count']} rich_generated={row['rich_generated_count']} "
                f"P={row['avg_precision']} R={row['avg_recall']} F1={row['avg_f1']}"
            )
        else:
            print(
                f"- {row['field']}: gold={row['gold_count']} generated={row['generated_count']} accurate={row['accurate_count']} "
                f"completeness={row['completeness']} accuracy={row['accuracy']} regularity={row['regularity']} "
                f"excluded={row['excluded_count']} rich_generated={row['rich_generated_count']}"
            )


if __name__ == "__main__":
    main()

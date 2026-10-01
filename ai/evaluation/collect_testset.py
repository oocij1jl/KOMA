"""Collect a balanced ISBN test set for KOMA evaluation.

The script builds:
  - a 500-book primary test set
  - a 50-book secondary validation subset selected from the 500 books

It intentionally uses only the Python standard library so it can run before the
backend environment is fully installed. API keys are read from `.env` and
`backend/.env`; values are never printed.

Usage:
  python ai/evaluation/collect_testset.py
  python ai/evaluation/collect_testset.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import parse, request


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "ai" / "evaluation" / "data" / "testsets"
DEFAULT_CACHE_DIR = ROOT_DIR / "ai" / "evaluation" / "data" / "testset_cache"

D4L_SEARCH_BOOKS_URL = "https://data4library.kr/api/srchBooks"
D4L_LOAN_ITEMS_URL = "https://data4library.kr/api/loanItemSrch"
NL_ISBN_URL = "https://www.nl.go.kr/seoji/SearchApi.do"

TARGET_TOTAL = 500
SECONDARY_TOTAL = 50
CATEGORY_QUOTAS = {
    "일반도서": 125,
    "번역서": 125,
    "복수저자": 125,
    "외국도서": 125,
}
KDC_QUOTAS = {str(index): 50 for index in range(10)}
SECONDARY_KDC_QUOTAS = {str(index): 5 for index in range(10)}

TRANSLATION_RE = re.compile(r"(옮김|번역|역주|역자|옮긴이|원작|translat)", re.IGNORECASE)
MULTI_AUTHOR_RE = re.compile(r"(;|,|·|ㆍ|/| 외\b|공저|공동|엮음|편저|글\s*;|그림\s*;)")
ASCII_RE = re.compile(r"[A-Za-z]{3,}")
ISBN_RE = re.compile(r"[^0-9Xx]")
TEXT_KEY_NOISE_RE = re.compile(r"[\s:;,.!?\-_/()\[\]{}『』「」《》〈〉·ㆍ]+")

# Broad keywords are used only to diversify the candidate pool. Final balancing
# is done with API-provided KDC and category heuristics.
KEYWORD_SEEDS = {
    "일반도서": [
        "철학",
        "종교",
        "사회",
        "경제",
        "과학",
        "기술",
        "예술",
        "언어",
        "문학",
        "역사",
    ],
    "번역서": [
        "세계문학",
        "번역",
        "고전",
        "심리학",
        "과학",
        "철학",
        "경제",
        "예술",
        "역사",
        "소설",
    ],
    "복수저자": [
        "공저",
        "앤솔러지",
        "대담",
        "논문",
        "에세이",
        "팀",
        "연구",
        "프로젝트",
        "시집",
        "그림책",
    ],
}


@dataclass
class Candidate:
    isbn: str
    title: str = ""
    author: str = ""
    publisher: str = ""
    publish_year: str = ""
    kdc: str = ""
    kdc_group: str = ""
    category: str = "일반도서"
    reference_available: bool = True
    marc_available: bool = False
    validation_tier: str = "primary"
    source: str = ""
    source_notes: str = ""
    nl_control_no: str = ""
    nl_bib_yn: str = ""


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"):
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip().strip('"').strip("'")
            values[key.strip()] = value
    return values


def is_real_key(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return "your_" not in lowered and "here" not in lowered


def cache_path(cache_dir: Path, namespace: str, key: str) -> Path:
    safe_key = re.sub(r"[^0-9A-Za-z가-힣_.-]+", "_", key)[:180]
    return cache_dir / namespace / f"{safe_key}.json"


def get_json(
    url: str,
    params: dict[str, Any],
    *,
    cache_dir: Path,
    namespace: str,
    cache_key: str,
    sleep_seconds: float,
    refresh: bool,
) -> dict[str, Any]:
    path = cache_path(cache_dir, namespace, cache_key)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    path.parent.mkdir(parents=True, exist_ok=True)
    full_url = f"{url}?{parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with request.urlopen(full_url, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            time.sleep(sleep_seconds)
            return payload
        except (urllib_error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"API request failed for {namespace}:{cache_key}: {last_error}")


def normalize_isbn(value: str) -> str:
    return ISBN_RE.sub("", value or "").upper()


def is_valid_isbn13(value: str) -> bool:
    if len(value) != 13 or not value.isdigit():
        return False
    total = sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(value[:12]))
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(value[12])


def unwrap_docs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    docs = payload.get("response", {}).get("docs", [])
    result: list[dict[str, Any]] = []
    for item in docs:
        if isinstance(item, dict) and isinstance(item.get("doc"), dict):
            result.append(item["doc"])
        elif isinstance(item, dict) and isinstance(item.get("book"), dict):
            result.append(item["book"])
        elif isinstance(item, dict):
            result.append(item)
    return result


def first_value(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def kdc_group(value: str) -> str:
    match = re.search(r"\d", value or "")
    return match.group(0) if match else ""


def classify_category(
    *,
    title: str,
    author: str,
    publisher: str,
    source_hint: str,
) -> str:
    haystack = " ".join([title, author, publisher, source_hint])
    if "외국도서" in source_hint or "oversea" in source_hint:
        return "외국도서"
    if TRANSLATION_RE.search(haystack):
        return "번역서"
    if MULTI_AUTHOR_RE.search(author):
        return "복수저자"
    if ASCII_RE.search(title) and ASCII_RE.search(publisher):
        return "외국도서"
    return "일반도서"


def candidate_from_d4l_doc(doc: dict[str, Any], *, source: str, source_hint: str) -> Candidate | None:
    isbn = normalize_isbn(first_value(doc, "isbn13", "isbn", "EA_ISBN"))
    if not is_valid_isbn13(isbn):
        return None

    title = first_value(doc, "bookname", "title", "TITLE")
    author = first_value(doc, "authors", "author", "AUTHOR")
    publisher = first_value(doc, "publisher", "PUBLISHER")
    publish_year = first_value(doc, "publication_year", "publish_year", "PUBLISH_YEAR")
    kdc = first_value(doc, "class_no", "kdc", "KDC")
    group = kdc_group(kdc)
    category = classify_category(title=title, author=author, publisher=publisher, source_hint=source_hint)

    return Candidate(
        isbn=isbn,
        title=title,
        author=author,
        publisher=publisher,
        publish_year=publish_year,
        kdc=kdc,
        kdc_group=group,
        category=category,
        reference_available=True,
        source=source,
        source_notes=source_hint,
    )


def merge_candidate(existing: Candidate, incoming: Candidate) -> Candidate:
    for field in ("title", "author", "publisher", "publish_year", "kdc", "kdc_group"):
        if not getattr(existing, field) and getattr(incoming, field):
            setattr(existing, field, getattr(incoming, field))
    if existing.category == "일반도서" and incoming.category != "일반도서":
        existing.category = incoming.category
    if incoming.source not in existing.source.split("|"):
        existing.source = "|".join(filter(None, [existing.source, incoming.source]))
    if incoming.source_notes and incoming.source_notes not in existing.source_notes:
        existing.source_notes = " | ".join(filter(None, [existing.source_notes, incoming.source_notes]))
    return existing


def collect_d4l_candidates(
    *,
    d4l_key: str,
    cache_dir: Path,
    refresh: bool,
    sleep_seconds: float,
    pages_per_kdc: int,
    keyword_pages: int,
) -> dict[str, Candidate]:
    candidates: dict[str, Candidate] = {}

    def add(candidate: Candidate | None) -> None:
        if candidate is None:
            return
        previous = candidates.get(candidate.isbn)
        candidates[candidate.isbn] = merge_candidate(previous, candidate) if previous else candidate

    for group in range(10):
        for page in range(1, pages_per_kdc + 1):
            params = {
                "authKey": d4l_key,
                "kdc": str(group),
                "pageNo": page,
                "pageSize": 100,
                "format": "json",
            }
            payload = get_json(
                D4L_LOAN_ITEMS_URL,
                params,
                cache_dir=cache_dir,
                namespace="d4l_loan",
                cache_key=f"kdc-{group}-page-{page}",
                sleep_seconds=sleep_seconds,
                refresh=refresh,
            )
            for doc in unwrap_docs(payload):
                add(candidate_from_d4l_doc(doc, source="d4l_loan", source_hint=f"kdc={group}"))

    for group in range(10):
        for page in range(1, max(2, pages_per_kdc // 2 + 1)):
            params = {
                "authKey": d4l_key,
                "kdc": str(group),
                "book_dvsn": "oversea",
                "pageNo": page,
                "pageSize": 100,
                "format": "json",
            }
            payload = get_json(
                D4L_LOAN_ITEMS_URL,
                params,
                cache_dir=cache_dir,
                namespace="d4l_loan_oversea",
                cache_key=f"kdc-{group}-oversea-page-{page}",
                sleep_seconds=sleep_seconds,
                refresh=refresh,
            )
            for doc in unwrap_docs(payload):
                add(candidate_from_d4l_doc(doc, source="d4l_oversea", source_hint=f"외국도서 oversea kdc={group}"))

    for seed_category, keywords in KEYWORD_SEEDS.items():
        for keyword in keywords:
            for page in range(1, keyword_pages + 1):
                params = {
                    "authKey": d4l_key,
                    "keyword": keyword,
                    "pageNo": page,
                    "pageSize": 50,
                    "format": "json",
                }
                payload = get_json(
                    D4L_SEARCH_BOOKS_URL,
                    params,
                    cache_dir=cache_dir,
                    namespace="d4l_search",
                    cache_key=f"{seed_category}-{keyword}-page-{page}",
                    sleep_seconds=sleep_seconds,
                    refresh=refresh,
                )
                for doc in unwrap_docs(payload):
                    hint = f"{seed_category} keyword={keyword}"
                    add(candidate_from_d4l_doc(doc, source="d4l_search", source_hint=hint))

    return candidates


def enrich_with_nl(
    candidates: dict[str, Candidate],
    *,
    nl_key: str,
    cache_dir: Path,
    refresh: bool,
    sleep_seconds: float,
    max_enrich: int | None,
) -> None:
    buckets: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for item in candidates.values():
        group = item.kdc_group if item.kdc_group in KDC_QUOTAS else "missing"
        buckets[(item.category, group)].append(item)

    for bucket_items in buckets.values():
        bucket_items.sort(key=lambda item: (item.title == "", item.author == "", item.isbn))

    items: list[Candidate] = []
    ordered_keys = [
        (category, group)
        for group in sorted([*KDC_QUOTAS.keys(), "missing"])
        for category in CATEGORY_QUOTAS
    ]
    while True:
        added = False
        for key in ordered_keys:
            bucket = buckets.get(key)
            if bucket:
                items.append(bucket.pop(0))
                added = True
        if not added:
            break

    if max_enrich is not None:
        items = items[:max_enrich]

    for index, candidate in enumerate(items, start=1):
        params = {
            "cert_key": nl_key,
            "result_style": "json",
            "page_no": 1,
            "page_size": 1,
            "isbn": candidate.isbn,
        }
        payload = get_json(
            NL_ISBN_URL,
            params,
            cache_dir=cache_dir,
            namespace="nl_isbn",
            cache_key=candidate.isbn,
            sleep_seconds=sleep_seconds,
            refresh=refresh,
        )
        docs = payload.get("docs", [])
        if not docs:
            continue
        doc = docs[0]
        candidate.title = candidate.title or first_value(doc, "TITLE")
        candidate.author = candidate.author or first_value(doc, "AUTHOR")
        candidate.publisher = candidate.publisher or first_value(doc, "PUBLISHER")
        candidate.publish_year = candidate.publish_year or first_value(doc, "PUBLISH_PREDATE")[:4]
        candidate.kdc = first_value(doc, "KDC") or candidate.kdc
        candidate.kdc_group = kdc_group(candidate.kdc) or candidate.kdc_group
        candidate.nl_control_no = first_value(doc, "CONTROL_NO")
        candidate.nl_bib_yn = first_value(doc, "BIB_YN")
        candidate.marc_available = bool(candidate.nl_control_no) and candidate.nl_bib_yn.upper() != "N"
        candidate.category = classify_category(
            title=candidate.title,
            author=candidate.author,
            publisher=candidate.publisher,
            source_hint=candidate.source_notes,
        )
        if index % 100 == 0:
            print(f"NL enrichment: {index}/{len(items)}")


def selection_score(candidate: Candidate) -> tuple[int, int, int, str]:
    return (
        1 if candidate.marc_available else 0,
        1 if candidate.kdc_group else 0,
        1 if candidate.title and candidate.author else 0,
        candidate.isbn,
    )


def duplicate_key(candidate: Candidate) -> str:
    title = TEXT_KEY_NOISE_RE.sub("", candidate.title or "").casefold()
    author = TEXT_KEY_NOISE_RE.sub("", candidate.author or "").casefold()
    if not title or not author:
        return ""
    return f"{title}|{author}"


def select_primary(candidates: list[Candidate]) -> tuple[list[Candidate], list[dict[str, str]]]:
    usable = [
        item
        for item in candidates
        if item.reference_available and item.kdc_group in KDC_QUOTAS and item.category in CATEGORY_QUOTAS
    ]
    usable.sort(key=selection_score, reverse=True)

    selected: list[Candidate] = []
    rejects: list[dict[str, str]] = []
    used: set[str] = set()
    used_duplicate_keys: set[str] = set()
    category_counts: Counter[str] = Counter()
    kdc_counts: Counter[str] = Counter()

    def take(item: Candidate) -> None:
        selected.append(item)
        used.add(item.isbn)
        key = duplicate_key(item)
        if key:
            used_duplicate_keys.add(key)
        category_counts[item.category] += 1
        kdc_counts[item.kdc_group] += 1

    def is_duplicate_title_author(item: Candidate) -> bool:
        key = duplicate_key(item)
        return bool(key and key in used_duplicate_keys)

    # Strict pass: category and KDC quotas must both have room.
    for item in usable:
        if len(selected) >= TARGET_TOTAL:
            break
        if is_duplicate_title_author(item):
            continue
        if category_counts[item.category] >= CATEGORY_QUOTAS[item.category]:
            continue
        if kdc_counts[item.kdc_group] >= KDC_QUOTAS[item.kdc_group]:
            continue
        take(item)

    # Relaxed pass: fill any holes while still avoiding severe KDC overrun.
    for item in usable:
        if len(selected) >= TARGET_TOTAL:
            break
        if item.isbn in used:
            continue
        if is_duplicate_title_author(item):
            continue
        if kdc_counts[item.kdc_group] >= KDC_QUOTAS[item.kdc_group] + 10:
            continue
        if category_counts[item.category] >= CATEGORY_QUOTAS[item.category] + 15:
            continue
        take(item)

    # Duplicate fallback: preserve the required 500-book shape even if a bucket
    # does not have enough unique title+author candidates.
    # Last resort: keep the set at 500 if the source data is imbalanced.
    for item in usable:
        if len(selected) >= TARGET_TOTAL:
            break
        if item.isbn not in used:
            take(item)

    for item in candidates:
        if item.isbn in used:
            continue
        reason = []
        if not item.reference_available:
            reason.append("reference_unavailable")
        if item.kdc_group not in KDC_QUOTAS:
            reason.append("missing_kdc_group")
        if item.category not in CATEGORY_QUOTAS:
            reason.append("unknown_category")
        if not reason:
            reason.append("quota_or_overflow")
        rejects.append({"isbn": item.isbn, "reason": ",".join(reason), "title": item.title})

    return selected, rejects


def mark_secondary(selected: list[Candidate]) -> list[Candidate]:
    secondary: list[Candidate] = []
    category_counts: Counter[str] = Counter()
    used: set[str] = set()
    by_group: dict[str, list[Candidate]] = defaultdict(list)
    for item in selected:
        if item.marc_available:
            by_group[item.kdc_group].append(item)

    for group, items in by_group.items():
        items.sort(key=selection_score, reverse=True)

    for group, quota in SECONDARY_KDC_QUOTAS.items():
        for item in by_group.get(group, []):
            if len([book for book in secondary if book.kdc_group == group]) >= quota:
                break
            if category_counts[item.category] >= 14:
                continue
            item.validation_tier = "secondary"
            secondary.append(item)
            used.add(item.isbn)
            category_counts[item.category] += 1

    # If a category-balancing constraint blocked a KDC group, fill by KDC anyway.
    for group, quota in SECONDARY_KDC_QUOTAS.items():
        current = len([book for book in secondary if book.kdc_group == group])
        for item in by_group.get(group, []):
            if current >= quota:
                break
            if item.isbn in used:
                continue
            item.validation_tier = "secondary"
            secondary.append(item)
            used.add(item.isbn)
            current += 1

    # Last resort if some KDC groups do not have enough MARC candidates.
    for item in sorted([book for book in selected if book.marc_available and book.isbn not in used], key=selection_score, reverse=True):
        if len(secondary) >= SECONDARY_TOTAL:
            break
        item.validation_tier = "secondary"
        secondary.append(item)
        used.add(item.isbn)

    return secondary[:SECONDARY_TOTAL]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def candidate_row(candidate: Candidate, index: int) -> dict[str, Any]:
    return {
        "id": f"KOMA-{index:04d}",
        "isbn": candidate.isbn,
        "category": candidate.category,
        "reference_available": str(candidate.reference_available).lower(),
        "marc_available": str(candidate.marc_available).lower(),
        "kdc_group": candidate.kdc_group,
        "validation_tier": candidate.validation_tier,
        "title": candidate.title,
        "author": candidate.author,
        "publisher": candidate.publisher,
        "publish_year": candidate.publish_year,
        "kdc": candidate.kdc,
        "nl_control_no": candidate.nl_control_no,
        "nl_bib_yn": candidate.nl_bib_yn,
        "source": candidate.source,
        "source_notes": candidate.source_notes,
    }


def build_summary(selected: list[Candidate], secondary: list[Candidate], pool_size: int) -> dict[str, Any]:
    duplicate_keys = [duplicate_key(item) for item in selected if duplicate_key(item)]
    duplicate_key_counts = Counter(duplicate_keys)
    duplicate_groups = {key: count for key, count in duplicate_key_counts.items() if count > 1}
    return {
        "pool_size": pool_size,
        "selected_total": len(selected),
        "secondary_total": len(secondary),
        "selected_by_category": dict(Counter(item.category for item in selected)),
        "selected_by_kdc_group": dict(sorted(Counter(item.kdc_group for item in selected).items())),
        "secondary_by_category": dict(Counter(item.category for item in secondary)),
        "secondary_by_kdc_group": dict(sorted(Counter(item.kdc_group for item in secondary).items())),
        "marc_available_in_selected": sum(1 for item in selected if item.marc_available),
        "duplicate_title_author_group_count": len(duplicate_groups),
        "duplicate_title_author_row_count": sum(duplicate_groups.values()),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect a 500 ISBN KOMA test set and a 50-book secondary MARC subset.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--refresh", action="store_true", help="Ignore cached API responses")
    parser.add_argument("--dry-run", action="store_true", help="Check keys and planned output paths without API calls")
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--pages-per-kdc", type=int, default=4)
    parser.add_argument("--keyword-pages", type=int, default=2)
    parser.add_argument("--max-nl-enrich", type=int, default=2400, help="Limit NL ISBN enrichment calls; use 0 for no limit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_env()
    d4l_key = env.get("D4L_API_KEY")
    nl_key = env.get("NL_API_KEY")

    missing = []
    if not is_real_key(d4l_key):
        missing.append("D4L_API_KEY")
    if not is_real_key(nl_key):
        missing.append("NL_API_KEY")
    if missing:
        raise SystemExit(
            "Missing API key(s): "
            + ", ".join(missing)
            + ". Add them to backend/.env or .env, then rerun this script."
        )

    print(f"Output dir: {args.output_dir}")
    print(f"Cache dir:  {args.cache_dir}")
    print("API keys: present")
    if args.dry_run:
        return

    candidates = collect_d4l_candidates(
        d4l_key=d4l_key or "",
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        sleep_seconds=args.sleep_seconds,
        pages_per_kdc=args.pages_per_kdc,
        keyword_pages=args.keyword_pages,
    )
    print(f"D4L candidate pool: {len(candidates)}")

    max_enrich = None if args.max_nl_enrich == 0 else args.max_nl_enrich
    enrich_with_nl(
        candidates,
        nl_key=nl_key or "",
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        sleep_seconds=args.sleep_seconds,
        max_enrich=max_enrich,
    )

    selected, rejects = select_primary(list(candidates.values()))
    secondary = mark_secondary(selected)
    summary = build_summary(selected, secondary, pool_size=len(candidates))

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
        "nl_control_no",
        "nl_bib_yn",
        "source",
        "source_notes",
    ]
    minimal_fields = ["id", "isbn", "category", "reference_available"]

    selected_rows = [candidate_row(item, index) for index, item in enumerate(selected, start=1)]
    secondary_isbns = {item.isbn for item in secondary}
    secondary_rows = [row for row in selected_rows if row["isbn"] in secondary_isbns]

    write_csv(args.output_dir / "testset_500.csv", selected_rows, full_fields)
    write_csv(args.output_dir / "testset_500_minimal.csv", selected_rows, minimal_fields)
    write_csv(args.output_dir / "testset_secondary_50.csv", secondary_rows, full_fields)
    write_csv(args.output_dir / "testset_rejects.csv", rejects, ["isbn", "reason", "title"])
    (args.output_dir / "testset_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote: {args.output_dir / 'testset_500.csv'}")
    print(f"Wrote: {args.output_dir / 'testset_secondary_50.csv'}")


if __name__ == "__main__":
    main()

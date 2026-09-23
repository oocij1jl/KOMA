"""팀원이 주는 ISBN CSV(id, isbn, category, reference_available)를 KOMA
bulk generate API로 대량 처리하고, gold MARC 없이도 측정 가능한 지표를
집계한다.

evaluate_koma.py(33권 gold MARC와 필드 단위 정확도 비교)와는 별개 스크립트다.
대량으로 받는 ISBN은 대부분 비교 가능한 gold MARC가 없어서 field-by-field
정확도를 낼 수 없다. 대신 다음을 gold 없이 집계한다:
  - ISBN 조회/생성 성공률, 실패 사유(error_code)별 분포
  - 필드별 생성률 (020/245/260/700/710/653/056/082/041/500/546)
  - /api/validate 기반 구조 검증 통과율
  - ai_inference 필드의 evidence 누락 여부
  - category별 성공률
  - 처리 시간

그리고 category별 층화추출로 수동 검수용 표본(reference_available=True를
우선)을 뽑아 리뷰 시트를 만든다 — 국가자료종합목록 "마크 보기"로 사람이
직접 대조하는 용도다.

사용 예:
  python ai/evaluation/evaluate_bulk.py --isbn-csv testset.csv
  python ai/evaluation/evaluate_bulk.py --isbn-csv testset.csv --skip-generate  # 캐시된 결과만 재집계
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import request as urllib_request

ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = ROOT_DIR / "eval_bulk_results"
DEFAULT_SUMMARY_JSON = ROOT_DIR / "eval_bulk_summary.json"
DEFAULT_SUMMARY_CSV = ROOT_DIR / "eval_bulk_summary.csv"
DEFAULT_SAMPLE_CSV = ROOT_DIR / "eval_bulk_review_sample.csv"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

BULK_BATCH_SIZE = 10  # backend GenerateBulkRequest 상한과 동일해야 함
REQUIRED_TAGS = ("020", "245", "260")
TRACKED_TAGS = ("020", "245", "260", "700", "710", "653", "056", "082", "041", "500", "546")


@dataclass
class IsbnRow:
    id: str
    isbn: str
    category: str
    reference_available: bool


def read_isbn_csv(path: Path) -> list[IsbnRow]:
    rows: list[IsbnRow] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            isbn = (raw.get("isbn") or "").strip()
            if not isbn or isbn in seen:
                continue
            seen.add(isbn)
            ref_raw = (raw.get("reference_available") or "").strip().lower()
            rows.append(
                IsbnRow(
                    id=(raw.get("id") or "").strip(),
                    isbn=isbn,
                    category=(raw.get("category") or "").strip() or "미분류",
                    reference_available=ref_raw in {"true", "1", "y", "yes"},
                )
            )
    return rows


def chunked(items: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def call_generate_bulk(base_url: str, isbns: list[str]) -> list[dict[str, Any]]:
    payload = json.dumps({"isbns": isbns}, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        f"{base_url.rstrip('/')}/api/generate/marc/bulk",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=600) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)["results"]


def call_validate(base_url: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    payload_fields = [
        {
            "tag": field["tag"],
            "ind1": field.get("indicator1", " "),
            "ind2": field.get("indicator2", " "),
            "subfields": field.get("subfields", []),
        }
        for field in fields
    ]
    payload = json.dumps({"fields": payload_fields}, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        f"{base_url.rstrip('/')}/api/validate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def ensure_results_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def collect_results(
    rows: list[IsbnRow],
    *,
    base_url: str,
    results_dir: Path,
    sleep_seconds: float,
    force_regenerate: bool,
    batch_size: int = BULK_BATCH_SIZE,
) -> None:
    ensure_results_dir(results_dir)
    pending = [row for row in rows if force_regenerate or not (results_dir / f"{row.isbn}.json").exists()]
    if not pending:
        return

    for batch in chunked(pending, batch_size):
        isbns = [row.isbn for row in batch]
        try:
            items = call_generate_bulk(base_url, isbns)
        except (urllib_error.HTTPError, urllib_error.URLError) as exc:
            for isbn in isbns:
                error_payload = {
                    "isbn": isbn,
                    "status": "error",
                    "error_code": "request_failed",
                    "error_message": str(exc),
                }
                (results_dir / f"{isbn}.json").write_text(
                    json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            time.sleep(sleep_seconds)
            continue

        for item in items:
            isbn = item.get("isbn")
            if item.get("status") == "success":
                try:
                    item["validation"] = call_validate(base_url, item["result"]["fields"])
                except (urllib_error.HTTPError, urllib_error.URLError) as exc:
                    item["validation"] = {"valid": None, "error": str(exc)}
            (results_dir / f"{isbn}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        time.sleep(sleep_seconds)


def load_cached_results(results_dir: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    if not results_dir.exists():
        return results
    for path in sorted(results_dir.glob("*.json")):
        try:
            results[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return results


def compute_metrics(rows: list[IsbnRow], cached: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    status_counts: Counter[str] = Counter()
    error_code_counts: Counter[str] = Counter()
    field_present_counts: Counter[str] = Counter()
    field_skip_counts: Counter[str] = Counter()
    validation_pass = 0
    validation_fail = 0
    validation_unknown = 0
    evidence_missing = 0
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        item = cached.get(row.isbn)
        if item is None:
            status_counts["not_processed"] += 1
            category_counts[row.category]["not_processed"] += 1
            continue

        status = item.get("status", "unknown")
        status_counts[status] += 1
        category_counts[row.category][status] += 1
        if status != "success":
            error_code_counts[item.get("error_code", "unknown")] += 1
            continue

        result = item.get("result", {})
        for field in result.get("fields", []):
            tag = field.get("tag")
            field_present_counts[tag] += 1
            if field.get("source") == "ai_inference":
                evidence = field.get("evidence")
                if not evidence or not evidence.get("reasoning"):
                    evidence_missing += 1
        for skipped in result.get("skipped_fields", []):
            field_skip_counts[skipped.get("tag")] += 1

        validation = item.get("validation")
        if not validation or validation.get("valid") is None:
            validation_unknown += 1
        elif validation.get("valid"):
            validation_pass += 1
        else:
            validation_fail += 1

    success_count = status_counts.get("success", 0)

    def _rate(tag: str) -> float | None:
        return round(field_present_counts.get(tag, 0) / success_count, 4) if success_count else None

    return {
        "total_isbns": total,
        "processed": sum(status_counts.values()),
        "status_counts": dict(status_counts),
        "error_code_counts": dict(error_code_counts),
        "success_rate": round(success_count / total, 4) if total else None,
        "required_field_presence_rate": {tag: _rate(tag) for tag in REQUIRED_TAGS},
        "field_presence_rate": {tag: _rate(tag) for tag in TRACKED_TAGS},
        "field_skip_counts": dict(field_skip_counts),
        "validation": {
            "pass": validation_pass,
            "fail": validation_fail,
            "unknown": validation_unknown,
            "pass_rate": round(validation_pass / success_count, 4) if success_count else None,
        },
        "evidence_missing_count": evidence_missing,
        "by_category": {category: dict(counts) for category, counts in sorted(category_counts.items())},
    }


def write_summary_csv(metrics: dict[str, Any], path: Path) -> None:
    rows: list[dict[str, Any]] = [
        {"metric": "total_isbns", "value": metrics["total_isbns"]},
        {"metric": "processed", "value": metrics["processed"]},
        {"metric": "success_rate", "value": metrics["success_rate"]},
        {"metric": "elapsed_seconds", "value": metrics.get("elapsed_seconds")},
        {"metric": "avg_seconds_per_isbn", "value": metrics.get("avg_seconds_per_isbn")},
    ]
    for code, count in sorted(metrics["error_code_counts"].items()):
        rows.append({"metric": f"error.{code}", "value": count})
    for tag, rate in metrics["field_presence_rate"].items():
        rows.append({"metric": f"field_presence.{tag}", "value": rate})
    rows.append({"metric": "validation.pass_rate", "value": metrics["validation"]["pass_rate"]})
    rows.append({"metric": "validation.fail_count", "value": metrics["validation"]["fail"]})
    rows.append({"metric": "evidence_missing_count", "value": metrics["evidence_missing_count"]})
    for category, counts in metrics["by_category"].items():
        rows.append({"metric": f"category.{category}.success", "value": counts.get("success", 0)})

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(rows)


def stratified_sample(
    rows: list[IsbnRow],
    cached: dict[str, dict[str, Any]],
    *,
    per_category: int,
    seed: int = 42,
) -> list[IsbnRow]:
    """category별로 최대 per_category권을 뽑는다. reference_available=True인
    행을 우선 채택한다(국가자료종합목록 등에서 비교 대상을 구할 가능성이 더 높음)."""
    by_category: dict[str, list[IsbnRow]] = defaultdict(list)
    for row in rows:
        item = cached.get(row.isbn)
        if item and item.get("status") == "success":
            by_category[row.category].append(row)

    rng = random.Random(seed)
    sample: list[IsbnRow] = []
    for category, candidates in sorted(by_category.items()):
        preferred = [row for row in candidates if row.reference_available]
        others = [row for row in candidates if not row.reference_available]
        rng.shuffle(preferred)
        rng.shuffle(others)
        sample.extend((preferred + others)[:per_category])
    return sample


def _format_field(field: dict[str, Any]) -> str:
    subfield_text = "".join(f"${sf.get('code', '')}{sf.get('value', '')}" for sf in field.get("subfields", []))
    return f"{field.get('tag', '')}{subfield_text}"


def export_review_sheet(sample: list[IsbnRow], cached: dict[str, dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "id",
        "isbn",
        "category",
        "reference_available",
        "generated_fields",
        "skipped_fields",
        "reviewer_verdict",
        "reviewer_notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sample:
            item = cached.get(row.isbn, {})
            result = item.get("result", {})
            fields_text = " | ".join(_format_field(field) for field in result.get("fields", []))
            skipped_text = ", ".join(
                f"{skipped.get('tag')}({skipped.get('reason')})" for skipped in result.get("skipped_fields", [])
            )
            writer.writerow(
                {
                    "id": row.id,
                    "isbn": row.isbn,
                    "category": row.category,
                    "reference_available": row.reference_available,
                    "generated_fields": fields_text,
                    "skipped_fields": skipped_text,
                    "reviewer_verdict": "",
                    "reviewer_notes": "",
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-generate KOMA MARC results from a plain ISBN CSV (no gold MARC) "
        "and aggregate reference-free metrics + a stratified manual-review sample."
    )
    parser.add_argument("--isbn-csv", type=Path, required=True, help="id,isbn,category,reference_available 컬럼을 가진 CSV")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY_JSON)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--sample-csv", type=Path, default=DEFAULT_SAMPLE_CSV)
    parser.add_argument("--sample-per-category", type=int, default=5)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--skip-generate", action="store_true", help="캐시된 결과만 재집계, 새로 호출하지 않음")
    parser.add_argument("--force-regenerate", action="store_true", help="캐시 무시하고 전부 재호출")
    parser.add_argument("--limit", type=int, default=None, help="CSV 앞에서 N행만 사용(리허설용)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_isbn_csv(args.isbn_csv)
    if args.limit is not None:
        rows = rows[: args.limit]

    print(f"ISBN CSV: {args.isbn_csv}")
    print(f"Rows: {len(rows)}")

    elapsed = 0.0
    if not args.skip_generate:
        start = time.time()
        collect_results(
            rows,
            base_url=args.base_url,
            results_dir=args.results_dir,
            sleep_seconds=args.sleep_seconds,
            force_regenerate=args.force_regenerate,
        )
        elapsed = time.time() - start

    cached = load_cached_results(args.results_dir)
    metrics = compute_metrics(rows, cached)
    metrics["elapsed_seconds"] = round(elapsed, 2)
    metrics["avg_seconds_per_isbn"] = round(elapsed / len(rows), 2) if rows and elapsed else None

    args.summary_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary_csv(metrics, args.summary_csv)

    sample = stratified_sample(rows, cached, per_category=args.sample_per_category)
    export_review_sheet(sample, cached, args.sample_csv)

    print()
    print(f"Processed: {metrics['processed']} / {metrics['total_isbns']}")
    print(f"Success rate: {metrics['success_rate']}")
    print(f"Error breakdown: {metrics['error_code_counts']}")
    print(f"Validation pass rate: {metrics['validation']['pass_rate']} (fail={metrics['validation']['fail']})")
    print(f"Evidence missing count: {metrics['evidence_missing_count']}")
    print()
    print(f"Summary JSON: {args.summary_json}")
    print(f"Summary CSV:  {args.summary_csv}")
    print(f"Review sample ({len(sample)} books): {args.sample_csv}")


if __name__ == "__main__":
    main()

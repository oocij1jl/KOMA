"""생성 결과 디렉터리의 필드 현황을 추적 가능한 스냅샷으로 남긴다.

목적은 MARC 품질/RAG 개선 전후를 같은 기준으로 비교하는 것이다. 이 스크립트는
결과 JSON(GenerateResult)과 gold MARC를 읽기만 하고 어떤 원본도 수정하지 않는다.
외부 API나 LLM도 호출하지 않는다.

출력 파일

- ``manifest.json``        실행 조건, 입력 파일 해시, 필드 정책, RAG 규칙 보유 현황
- ``field_inventory.csv``  태그별 생성/ gold 보유 현황과 현재 생성 경로
- ``book_field_matrix.csv`` 도서 x 태그 단위 생성 횟수, source 라벨, skip 사유

사용 예

    python ai/evaluation/baseline_snapshot.py --label mid-presentation

    python ai/evaluation/baseline_snapshot.py \
        --label after-rule-layer \
        --results-dir ai/evaluation/runs/after-rule-layer/results
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import platform
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_MRC = ROOT_DIR / "docs" / "0428_희망샘도서관4월희망(33)OEM55126-OEM55158.mrc"
DEFAULT_RESULTS_DIR = ROOT_DIR / "mid_result" / "eval_results"
DEFAULT_OUT_ROOT = ROOT_DIR / "ai" / "evaluation" / "baseline"
GENERATE_OPTIONS_PATH = ROOT_DIR / "backend" / "schemas" / "llm.py"
RAG_CHUNKS_DIR = ROOT_DIR / "ai" / "rag" / "chunks"

# output_validator._assign_generated_by가 이 태그 집합만 "api"로 사후 표기한다.
# 값 자체는 현재 모든 태그가 LLM 1회 출력에서 나온다.
BIBLIO_API_TAGS = ("020", "245", "260", "700", "710")

POLICY_FIELDS = (
    "required_fields",
    "review_required_fields",
    "conditional_fields",
    "skipped_by_default",
)
POLICY_LABELS = {
    "required_fields": "required",
    "review_required_fields": "review_required",
    "conditional_fields": "conditional",
    "skipped_by_default": "skipped_by_default",
}


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _string_list(node: ast.AST) -> list[str] | None:
    """`["020", "245"]` 형태의 리터럴 리스트만 문자열 목록으로 바꾼다."""

    if not isinstance(node, ast.List):
        return None

    values: list[str] = []
    for element in node.elts:
        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
            return None
        values.append(element.value)
    return values


def _default_factory_list(node: ast.AST) -> list[str] | None:
    """`Field(default_factory=lambda: [...])`에서 태그 목록을 꺼낸다."""

    if not isinstance(node, ast.Call):
        return None

    for keyword in node.keywords:
        if keyword.arg != "default_factory":
            continue
        factory = keyword.value
        if isinstance(factory, ast.Lambda):
            return _string_list(factory.body)
    return None


def load_field_policy(path: Path) -> dict[str, list[str]]:
    """backend/schemas/llm.py의 GenerateOptions 기본값을 읽는다.

    백엔드 의존 패키지 없이도 동작해야 하므로 import 대신 AST로 읽는다.
    기본값 형태가 바뀌면 조용히 빈 값으로 넘어가지 않고 예외를 낸다.
    """

    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(module):
        if not isinstance(node, ast.ClassDef) or node.name != "GenerateOptions":
            continue

        policy: dict[str, list[str]] = {}
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
                continue
            name = statement.target.id
            if name not in POLICY_FIELDS or statement.value is None:
                continue
            tags = _default_factory_list(statement.value)
            if tags is not None:
                policy[name] = tags

        missing = [name for name in POLICY_FIELDS if name not in policy]
        if missing:
            raise SystemExit(f"GenerateOptions 기본값을 읽지 못했습니다: {', '.join(missing)} ({path})")
        return policy

    raise SystemExit(f"GenerateOptions 클래스를 찾지 못했습니다: {path}")


def load_rag_inventory(chunks_dir: Path) -> dict[str, dict[str, Any]]:
    """태그별 RAG 청크 파일의 존재 여부와 청크 수를 센다."""

    inventory: dict[str, dict[str, Any]] = {}
    if not chunks_dir.exists():
        return inventory

    for path in sorted(chunks_dir.glob("kormarc-*.jsonl")):
        tag = path.stem.removeprefix("kormarc-")
        chunk_count = 0
        malformed = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError:
                malformed += 1
                continue
            chunk_count += 1

        inventory[tag] = {
            "path": path.relative_to(ROOT_DIR).as_posix(),
            "chunk_count": chunk_count,
            "malformed_line_count": malformed,
            "sha256": sha256_of(path),
        }
    return inventory


def load_results(results_dir: Path) -> dict[str, dict[str, Any]]:
    """<ISBN>.json 형식의 GenerateResult 파일을 읽는다."""

    results: dict[str, dict[str, Any]] = {}
    for path in sorted(results_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"결과 JSON 파싱 실패: {path} ({exc.msg})") from exc
        if isinstance(payload, dict):
            results[path.stem] = payload
    return results


def field_rows(results: dict[str, dict[str, Any]]) -> tuple[Counter[str], Counter[str], dict[str, Counter[str]]]:
    """태그별 생성 도서 수, 발생 횟수, source 라벨 분포를 센다."""

    books_with_tag: Counter[str] = Counter()
    occurrences: Counter[str] = Counter()
    source_labels: dict[str, Counter[str]] = defaultdict(Counter)

    for payload in results.values():
        fields = payload.get("fields")
        if not isinstance(fields, list):
            continue

        seen_tags: set[str] = set()
        for field in fields:
            if not isinstance(field, dict):
                continue
            tag = str(field.get("tag", ""))
            if not tag:
                continue
            occurrences[tag] += 1
            seen_tags.add(tag)
            source_labels[tag][str(field.get("source", ""))] += 1
        for tag in seen_tags:
            books_with_tag[tag] += 1

    return books_with_tag, occurrences, source_labels


def skip_rows(results: dict[str, dict[str, Any]]) -> tuple[Counter[str], dict[str, Counter[str]]]:
    """태그별 skip 도서 수와 사유 분포를 센다."""

    skipped_books: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = defaultdict(Counter)

    for payload in results.values():
        skipped = payload.get("skipped_fields")
        if not isinstance(skipped, list):
            continue

        seen_tags: set[str] = set()
        for item in skipped:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag", ""))
            if not tag:
                continue
            seen_tags.add(tag)
            reasons[tag][str(item.get("reason", ""))] += 1
        for tag in seen_tags:
            skipped_books[tag] += 1

    return skipped_books, reasons


def gold_inventory(gold_mrc: Path) -> tuple[dict[str, dict[str, int]], list[str], str]:
    """gold MARC의 태그별 보유 도서 수와 발생 횟수를 센다.

    evaluate_koma의 파서를 그대로 써서 평가기와 같은 레코드 해석을 유지한다.
    """

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import evaluate_koma  # noqa: PLC0415 - 평가기와 동일한 파서를 재사용한다.
    finally:
        sys.path.pop(0)

    records = evaluate_koma.parse_gold_records(gold_mrc)
    if not records:
        raise SystemExit(f"gold MARC에서 레코드를 읽지 못했습니다: {gold_mrc}")

    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"books": 0, "occurrences": 0})
    for record in records:
        for tag, occurrences in record.tags.items():
            counts[tag]["books"] += 1
            counts[tag]["occurrences"] += len(occurrences)

    evaluated_fields = list(evaluate_koma.EVALUATED_FIELDS)
    return dict(counts), [record.isbn for record in records], ",".join(evaluated_fields)


def git_commit(root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip()


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_field_inventory(
    *,
    policy: dict[str, list[str]],
    rag: dict[str, dict[str, Any]],
    gold_counts: dict[str, dict[str, int]],
    books_with_tag: Counter[str],
    occurrences: Counter[str],
    source_labels: dict[str, Counter[str]],
    skipped_books: Counter[str],
    evaluated_fields: str,
) -> list[dict[str, Any]]:
    policy_by_tag: dict[str, str] = {}
    for policy_name in POLICY_FIELDS:
        for tag in policy[policy_name]:
            policy_by_tag[tag] = POLICY_LABELS[policy_name]

    generation_tags = {
        tag
        for policy_name in ("required_fields", "review_required_fields", "conditional_fields")
        for tag in policy[policy_name]
    } - set(policy["skipped_by_default"])

    evaluated = set(evaluated_fields.split(","))
    all_tags = sorted(set(policy_by_tag) | set(gold_counts) | set(books_with_tag) | set(rag))

    rows: list[dict[str, Any]] = []
    for tag in all_tags:
        gold = gold_counts.get(tag, {"books": 0, "occurrences": 0})
        rag_entry = rag.get(tag)
        prompt_rule = bool(rag_entry) and tag in generation_tags
        sources = source_labels.get(tag, Counter())

        rows.append(
            {
                "tag": tag,
                "config_policy": policy_by_tag.get(tag, "not_configured"),
                "prompt_generation_target": tag in generation_tags,
                "rag_chunk_file": rag_entry["path"] if rag_entry else "",
                "rag_chunk_count": rag_entry["chunk_count"] if rag_entry else 0,
                "rag_rule_reaches_prompt": prompt_rule,
                "current_generation_path": "llm" if tag in generation_tags else "not_generated",
                "source_label_in_results": ";".join(
                    f"{label or 'unset'}={count}" for label, count in sorted(sources.items())
                ),
                "generated_books": books_with_tag.get(tag, 0),
                "generated_occurrences": occurrences.get(tag, 0),
                "skipped_books": skipped_books.get(tag, 0),
                "gold_books": gold["books"],
                "gold_occurrences": gold["occurrences"],
                "evaluated_by_evaluate_koma": tag in evaluated,
            }
        )
    return rows


def build_book_matrix(results: dict[str, dict[str, Any]], gold_isbns: list[str]) -> list[dict[str, Any]]:
    gold_order = {isbn: index for index, isbn in enumerate(gold_isbns)}
    rows: list[dict[str, Any]] = []

    for isbn in sorted(results, key=lambda value: (gold_order.get(value, len(gold_order)), value)):
        payload = results[isbn]
        fields = payload.get("fields") if isinstance(payload.get("fields"), list) else []
        skipped = payload.get("skipped_fields") if isinstance(payload.get("skipped_fields"), list) else []

        per_tag: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "sources": Counter(), "generated_by": Counter(), "review_required": 0}
        )
        for field in fields:
            if not isinstance(field, dict):
                continue
            tag = str(field.get("tag", ""))
            if not tag:
                continue
            entry = per_tag[tag]
            entry["count"] += 1
            entry["sources"][str(field.get("source", ""))] += 1
            entry["generated_by"][str(field.get("generated_by", ""))] += 1
            if field.get("review_required"):
                entry["review_required"] += 1

        skip_reason_by_tag: dict[str, list[str]] = defaultdict(list)
        for item in skipped:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("tag", ""))
            if tag:
                skip_reason_by_tag[tag].append(str(item.get("reason", "")))

        for tag in sorted(set(per_tag) | set(skip_reason_by_tag)):
            entry = per_tag.get(tag)
            rows.append(
                {
                    "isbn": isbn,
                    "tag": tag,
                    "generated_count": entry["count"] if entry else 0,
                    "source_labels": ";".join(
                        f"{label or 'unset'}={count}" for label, count in sorted(entry["sources"].items())
                    )
                    if entry
                    else "",
                    "generated_by_labels": ";".join(
                        f"{label or 'unset'}={count}" for label, count in sorted(entry["generated_by"].items())
                    )
                    if entry
                    else "",
                    "review_required_count": entry["review_required"] if entry else 0,
                    "skip_reasons": " | ".join(skip_reason_by_tag.get(tag, [])),
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="생성 결과 디렉터리의 필드 현황 스냅샷을 만든다. 원본 파일은 수정하지 않는다."
    )
    parser.add_argument("--label", required=True, help="스냅샷 이름. 예: mid-presentation")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--gold-mrc", type=Path, default=DEFAULT_GOLD_MRC)
    parser.add_argument("--out-dir", type=Path, default=None, help="기본값: ai/evaluation/baseline/<label>")
    parser.add_argument(
        "--note",
        default="",
        help="이 스냅샷의 생성 조건 메모. 모델명, API 조회 시점 등 코드에서 알 수 없는 정보.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    results_dir: Path = args.results_dir
    if not results_dir.is_dir():
        raise SystemExit(f"결과 디렉터리가 없습니다: {results_dir}")

    out_dir: Path = args.out_dir or (DEFAULT_OUT_ROOT / args.label)
    out_dir.mkdir(parents=True, exist_ok=True)

    policy = load_field_policy(GENERATE_OPTIONS_PATH)
    rag = load_rag_inventory(RAG_CHUNKS_DIR)
    results = load_results(results_dir)
    if not results:
        raise SystemExit(f"결과 JSON이 없습니다: {results_dir}")

    gold_counts, gold_isbns, evaluated_fields = gold_inventory(args.gold_mrc)
    books_with_tag, occurrences, source_labels = field_rows(results)
    skipped_books, skip_reasons = skip_rows(results)

    inventory_rows = build_field_inventory(
        policy=policy,
        rag=rag,
        gold_counts=gold_counts,
        books_with_tag=books_with_tag,
        occurrences=occurrences,
        source_labels=source_labels,
        skipped_books=skipped_books,
        evaluated_fields=evaluated_fields,
    )
    matrix_rows = build_book_matrix(results, gold_isbns)

    write_csv(
        out_dir / "field_inventory.csv",
        [
            "tag",
            "config_policy",
            "prompt_generation_target",
            "rag_chunk_file",
            "rag_chunk_count",
            "rag_rule_reaches_prompt",
            "current_generation_path",
            "source_label_in_results",
            "generated_books",
            "generated_occurrences",
            "skipped_books",
            "gold_books",
            "gold_occurrences",
            "evaluated_by_evaluate_koma",
        ],
        inventory_rows,
    )
    write_csv(
        out_dir / "book_field_matrix.csv",
        [
            "isbn",
            "tag",
            "generated_count",
            "source_labels",
            "generated_by_labels",
            "review_required_count",
            "skip_reasons",
        ],
        matrix_rows,
    )

    manifest = {
        "label": args.label,
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": args.note,
        "git_commit": git_commit(ROOT_DIR),
        "python_version": platform.python_version(),
        "inputs": {
            "results_dir": results_dir.relative_to(ROOT_DIR).as_posix()
            if results_dir.is_relative_to(ROOT_DIR)
            else str(results_dir),
            "result_count": len(results),
            "gold_mrc": args.gold_mrc.relative_to(ROOT_DIR).as_posix()
            if args.gold_mrc.is_relative_to(ROOT_DIR)
            else str(args.gold_mrc),
            "gold_mrc_sha256": sha256_of(args.gold_mrc),
            "gold_record_count": len(gold_isbns),
            "result_file_sha256": {
                path.stem: sha256_of(path) for path in sorted(results_dir.glob("*.json"))
            },
        },
        "field_policy": policy,
        "biblio_api_tags_labelled_api": list(BIBLIO_API_TAGS),
        "evaluated_fields": evaluated_fields.split(","),
        "rag_chunks": rag,
        "skip_reasons": {tag: dict(counter) for tag, counter in sorted(skip_reasons.items())},
        "known_unknowns": [
            "생성 당시 LLM 모델명과 호출 파라미터는 결과 JSON에 없어 확인할 수 없다.",
            "생성 당시 API 조회 시점과 원본 응답이 저장되어 있지 않아 값 결측 여부를 사후 확인할 수 없다.",
            "생성 당시 D4L_SKIP_USAGE 설정값이 기록되어 있지 않다.",
        ],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"label: {args.label}")
    print(f"results: {len(results)} files from {results_dir}")
    print(f"gold records: {len(gold_isbns)} from {args.gold_mrc}")
    print(f"field rows: {len(inventory_rows)}, book-tag rows: {len(matrix_rows)}")
    print(f"output: {out_dir}")


if __name__ == "__main__":
    main()

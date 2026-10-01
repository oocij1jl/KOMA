"""정답 MARC가 확인된 ISBN만으로 평가용 데이터셋을 만든다.

`collect_gold_marc.py`가 저장한 레코드 디렉터리를 읽어, 요청한 권수만큼
ISBN-정답 쌍을 고정한다. 정답이 없는 ISBN은 넣지 않는다. 기존 표본의
분류 구성을 우선 유지하고, 모자란 만큼만 추가 후보에서 채운다.

출력
- ``dataset.csv``  생성 실행에 넣을 ISBN 목록(id,isbn,category,reference_available)
- ``gold.mrc``     같은 ISBN 집합의 정답 MARC(ISO 2709)
- ``manifest.json`` 출처·구성·검증 결과

사용 예

    python3 ai/evaluation/build_gold_testset.py \
        --primary-csv  <원래 500권 CSV> --primary-gold  <그 정답 레코드 디렉터리> \
        --extra-csv    <추가 후보 CSV>  --extra-gold    <추가 정답 레코드 디렉터리> \
        --books 500 --out-dir ai/evaluation/gold/<label>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_koma as v1  # noqa: E402

RECORD_TERMINATOR = b"\x1d"
FIELDNAMES = ["id", "isbn", "category", "reference_available"]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def gold_isbn(path: Path) -> str | None:
    records = v1.parse_gold_records(path)
    if len(records) != 1:
        return None
    return records[0].isbn or None


def available(rows: list[dict[str, str]], records_dir: Path) -> list[tuple[dict[str, str], Path]]:
    pairs: list[tuple[dict[str, str], Path]] = []
    for row in rows:
        isbn = (row.get("isbn") or "").strip()
        path = records_dir / f"{isbn}.mrc"
        if isbn and path.exists() and gold_isbn(path) == isbn:
            pairs.append((row, path))
    return pairs


def merge_gold(pairs: list[tuple[dict[str, str], Path]], destination: Path) -> list[str]:
    """선택한 레코드를 병합하고, 병합본에서 실제로 읽히는 ISBN만 돌려준다."""

    destination.write_bytes(b"".join(
        chunk if chunk.endswith(RECORD_TERMINATOR) else chunk + RECORD_TERMINATOR
        for chunk in (path.read_bytes() for _, path in pairs)
    ))
    return [record.isbn for record in v1.parse_gold_records(destination)]


def build(args: argparse.Namespace) -> int:
    primary = available(read_rows(args.primary_csv), args.primary_gold)
    extra = available(read_rows(args.extra_csv), args.extra_gold) if args.extra_csv and args.extra_gold else []

    args.out_dir.mkdir(parents=True, exist_ok=True)
    gold_path = args.out_dir / "gold.mrc"
    primary_isbns = {row["isbn"] for row, _ in primary}
    pool = primary + [pair for pair in extra if pair[0]["isbn"] not in primary_isbns]

    # 개별 파일이 읽히더라도 병합 스트림에서 유실되는 레코드가 있다. 실제로 읽힌
    # ISBN만 남기고 남은 후보로 채워, 데이터셋 권수와 정답 권수를 일치시킨다.
    chosen: list[tuple[dict[str, str], Path]] = []
    dropped: list[str] = []
    cursor = 0
    while len(chosen) < args.books and cursor < len(pool):
        need = args.books - len(chosen)
        chosen.extend(pool[cursor : cursor + need])
        cursor += need
        readable = set(merge_gold(chosen, gold_path))
        dropped.extend(row["isbn"] for row, _ in chosen if row["isbn"] not in readable)
        chosen = [pair for pair in chosen if pair[0]["isbn"] in readable]

    if len(chosen) < args.books:
        gold_path.unlink(missing_ok=True)
        print(
            f"정답이 확인된 ISBN이 {len(chosen)}권뿐입니다. 요청한 {args.books}권을 만들 수 없습니다. "
            f"(원표본 {len(primary)} / 추가 후보 {len(extra)} / 병합 유실 {len(dropped)})",
            file=sys.stderr,
        )
        return 1


    dataset_path = args.out_dir / "dataset.csv"
    with dataset_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for index, (row, _) in enumerate(chosen, start=1):
            writer.writerow({
                "id": f"GOLD-{index:04d}",
                "isbn": row["isbn"],
                "category": row.get("category", ""),
                "reference_available": "true",
            })

    parsed_isbns = merge_gold(chosen, gold_path)
    dataset_isbns = [row["isbn"] for row, _ in chosen]
    if sorted(parsed_isbns) != sorted(dataset_isbns):
        gold_path.unlink(missing_ok=True)
        print("병합한 정답과 데이터셋 ISBN이 일치하지 않습니다.", file=sys.stderr)
        return 1


    manifest: dict[str, Any] = {
        "books": len(chosen),
        "gold_source": "nl.go.kr 소장자료 목록 MARC 다운로드",
        "from_primary_sample": sum(1 for row, _ in chosen if row["isbn"] in primary_isbns),
        "from_extra_candidates": sum(1 for row, _ in chosen if row["isbn"] not in primary_isbns),
        "dropped_in_merge": dropped,
        "by_category": dict(Counter(row.get("category", "") for row, _ in chosen)),
        "dataset": dataset_path.name,
        "gold_mrc": gold_path.name,
        "note": "정답이 확인된 ISBN만 포함한다. 생성 결과에서 정답을 만들지 않는다.",
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(chosen)}권 확정: {dataset_path}, {gold_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-csv", type=Path, required=True)
    parser.add_argument("--primary-gold", type=Path, required=True)
    parser.add_argument("--extra-csv", type=Path)
    parser.add_argument("--extra-gold", type=Path)
    parser.add_argument("--books", type=int, default=500)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.books < 1:
        parser.error("books must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(build(parse_args()))

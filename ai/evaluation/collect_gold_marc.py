"""ISBN 목록으로 국립중앙도서관 소장자료 목록의 정답 MARC를 수집한다.

생성 결과(가설)와 정답(기준)을 섞지 않기 위해 이 스크립트는 KOMA 생성 결과를
읽지 않는다. 정답은 공개 목록 페이지에서만 가져온다.

  1) ISBN -> 레코드 키   GET /NL/contents/search.do?detailSearch=true&isbnOp=isbn&isbnCode=<ISBN>
  2) 레코드 키 -> MARC   GET /NL/marcDownload.do?downData=<viewKey>,<viewType>

받은 바이트는 ISO 2709 그대로 저장한다. 레코드의 020$a가 요청한 ISBN과 다르면
저장하지 않는다. 검색 결과가 여러 건이면 판·권차 모호성이므로 건너뛰고 사유를
기록한다. 추정으로 채우지 않는다.

사용 예

    python3 ai/evaluation/collect_gold_marc.py \
        --isbn-csv ai/evaluation/runs/<run>/500/dataset/testset_500_minimal.csv \
        --out-dir ai/evaluation/gold/<label>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evaluate_koma as v1  # noqa: E402

SEARCH_URL = "https://www.nl.go.kr/NL/contents/search.do"
MARC_URL = "https://www.nl.go.kr/NL/marcDownload.do"
USER_AGENT = "Mozilla/5.0 (compatible; KOMA-evaluation/1.0)"
VIEW_KEY_RE = re.compile(r"viewKey=(\d+)&viewType=([A-Za-z0-9]+)")
RECORD_TERMINATOR = b"\x1d"


def read_isbns(path: Path) -> list[str]:
    rows = [row.isbn for row in _read_rows(path)]
    unique = list(dict.fromkeys(rows))
    if len(unique) != len(rows):
        raise SystemExit(f"중복 ISBN이 있습니다: {len(rows)}행 / 고유 {len(unique)}개")
    return unique


def _read_rows(path: Path) -> list[Any]:
    import evaluate_bulk  # noqa: PLC0415 - 선택적 의존

    return evaluate_bulk.read_isbn_csv(path)


def find_record_key(client: httpx.Client, isbn: str) -> tuple[tuple[str, str] | None, str | None]:
    response = client.get(SEARCH_URL, params={"detailSearch": "true", "isbnOp": "isbn", "isbnCode": isbn})
    response.raise_for_status()
    keys = list(dict.fromkeys(VIEW_KEY_RE.findall(response.text)))
    if not keys:
        return None, "not_found"
    if len(keys) > 1:
        return None, f"ambiguous_{len(keys)}_records"
    return keys[0], None


def fetch_marc(client: httpx.Client, view_key: str, view_type: str) -> bytes:
    response = client.get(MARC_URL, params={"downData": f"{view_key},{view_type}"})
    response.raise_for_status()
    return response.content


def record_isbns(path: Path) -> set[str]:
    isbns: set[str] = set()
    for record in v1.parse_gold_records(path):
        if record.isbn:
            isbns.add(record.isbn)
    return isbns


def collect(args: argparse.Namespace) -> int:
    isbns = read_isbns(args.isbn_csv)
    records_dir = args.out_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    state_path = args.out_dir / "collection.json"
    state: dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    collected: dict[str, Any] = state.get("collected", {})
    rejected: dict[str, Any] = state.get("rejected", {})

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for index, isbn in enumerate(isbns, start=1):
            target = records_dir / f"{isbn}.mrc"
            if isbn in collected and target.exists():
                continue
            rejected.pop(isbn, None)
            try:
                key, reason = find_record_key(client, isbn)
                if key is None:
                    rejected[isbn] = {"reason": reason}
                else:
                    view_key, view_type = key
                    payload = fetch_marc(client, view_key, view_type)
                    target.write_bytes(payload)
                    found = record_isbns(target)
                    if isbn not in found:
                        target.unlink()
                        rejected[isbn] = {"reason": "isbn_mismatch", "record_isbns": sorted(found), "view_key": view_key}
                    else:
                        collected[isbn] = {"view_key": view_key, "view_type": view_type, "bytes": len(payload)}
            except httpx.HTTPError as exc:
                rejected[isbn] = {"reason": "http_error", "detail": str(exc)}
            state = {"source": "nl.go.kr 소장자료 목록", "requested": len(isbns),
                     "collected": collected, "rejected": rejected}
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            if index % 25 == 0 or index == len(isbns):
                print(f"{index}/{len(isbns)}: 수집 {len(collected)} / 미수집 {len(rejected)}", flush=True)
            time.sleep(args.sleep_seconds)

    merged = args.out_dir / "gold.mrc"
    chunks = [
        (records_dir / f"{isbn}.mrc").read_bytes()
        for isbn in isbns
        if isbn in collected and (records_dir / f"{isbn}.mrc").exists()
    ]
    merged.write_bytes(b"".join(chunk if chunk.endswith(RECORD_TERMINATOR) else chunk + RECORD_TERMINATOR for chunk in chunks))
    parsed = v1.parse_gold_records(merged)
    print(f"수집 {len(collected)} / 요청 {len(isbns)}; 병합 레코드 {len(parsed)}: {merged}")
    if rejected:
        print(f"미수집 {len(rejected)}권. 사유는 {state_path}에 기록했다.")
    return 0 if len(parsed) == len(isbns) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isbn-csv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=40.0)
    args = parser.parse_args()
    if args.sleep_seconds < 0:
        parser.error("sleep-seconds must be nonnegative")
    return args


if __name__ == "__main__":
    raise SystemExit(collect(parse_args()))

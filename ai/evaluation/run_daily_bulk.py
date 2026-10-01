"""Run fresh bulk evaluation in daily D4L-budgeted batches.

Uses the same per-book handler as /api/generate/marc/bulk. Successful ISBNs
are retained; failed ISBNs are retried on later days. No gold accuracy is inferred.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx
from ai.evaluation import evaluate_bulk as bulk
from backend.config import settings
from backend.routers.generate import _generate_one
from backend.routers.validate import ValidateRequest, validate_marc_fields

KST = ZoneInfo("Asia/Seoul")
logging.getLogger("httpx").setLevel(logging.WARNING)


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _assert_published_evidence_key(isbn: str, fields: list[dict]) -> None:
    """근거 키가 발행 계약(`from`)과 다르면 즉시 멈춘다.

    별칭 없이 직렬화하면 `from_`이 나가고, 검증·평가가 근거를 못 읽어 수백 권이
    조용히 오염된다. 한 권이라도 어긋나면 그 자리에서 실패시킨다.
    """
    for field in fields:
        evidence = field.get("evidence")
        if isinstance(evidence, dict) and "from" not in evidence:
            raise SystemExit(f"{isbn}: {field.get('tag')} 근거 키가 'from'이 아니다: {sorted(evidence)}")


def summarize(rows: list[bulk.IsbnRow], root: Path, state: dict) -> dict:
    cached = bulk.load_cached_results(root / "results")
    metrics = bulk.compute_metrics(rows, cached)
    metrics.update({"gold_available": False, "state": state})
    save_json(root / "summary.json", metrics)
    bulk.write_summary_csv(metrics, root / "summary.csv")
    sample = bulk.stratified_sample(rows, cached, per_category=5)
    bulk.export_review_sheet(sample, cached, root / "review_sample.csv")
    return metrics


async def run(args: argparse.Namespace) -> None:
    if not all((settings.OPENAI_API_KEY, settings.NL_API_KEY, settings.D4L_API_KEY)):
        raise SystemExit("OPENAI_API_KEY, NL_API_KEY and D4L_API_KEY are required")
    if settings.D4L_SKIP_USAGE:
        raise SystemExit("D4L_SKIP_USAGE must be false to preserve the 33-book collection conditions")
    if not 3 <= args.daily_call_budget <= 500:
        raise SystemExit("daily-call-budget must be between 3 and 500")
    rows = bulk.read_isbn_csv(args.isbn_csv)
    if len(rows) != 500:
        raise SystemExit(f"Expected 500 unique ISBNs, found {len(rows)}")
    root = args.out_dir
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        "day": datetime.now(KST).date().isoformat(),
        "d4l_requests": args.initial_used_calls,
        "paused_day": None,
        "attempted_today": [],
        "model": settings.OPENAI_MODEL,
        "conditions": "NL+D4L detail/keywords/usage+NL detail+Kyobo+OpenAI; Aladin optional",
    }
    if state["model"] != settings.OPENAI_MODEL:
        raise SystemExit("Model changed since this run began; use a separate output directory")
    save_json(state_path, state)
    print("Daily bulk evaluator ready", flush=True)
    sem = asyncio.Semaphore(1)
    upstream_errors: list[str] = []
    quota_errors: list[str] = []
    d4l_responses: list[dict] = []

    async def record_request(request: httpx.Request) -> None:
        if request.url.host == "data4library.kr":
            state["d4l_requests"] += 1
            save_json(state_path, state)

    async def record_response(response: httpx.Response) -> None:
        if response.request.url.host != "data4library.kr":
            return
        await response.aread()
        api_error = response.status_code >= 400
        is_quota = response.status_code == 429
        try:
            body = response.json()
            api_error = api_error or bool(body.get("error") or body.get("response", {}).get("error"))
            error_text = json.dumps(body, ensure_ascii=False).lower()
            is_quota = is_quota or (api_error and any(
                marker in error_text for marker in ("초과", "한도", "횟수", "quota", "rate limit", "too many")
            ))
        except (ValueError, AttributeError):
            api_error = True
        d4l_responses.append({"endpoint": response.request.url.path, "http_status": response.status_code,
                              "api_error": api_error, "quota": is_quota})
        if api_error:
            upstream_errors.append(response.request.url.path)
        if is_quota:
            quota_errors.append(response.request.url.path)

    async with httpx.AsyncClient(event_hooks={"request": [record_request], "response": [record_response]}) as client:
        while True:
            today = datetime.now(KST).date().isoformat()
            if state["day"] != today:
                state.update(day=today, d4l_requests=0, paused_day=None, attempted_today=[])
                save_json(state_path, state)
            cached = bulk.load_cached_results(root / "results")
            pending = [
                row for row in rows
                if cached.get(row.isbn, {}).get("status") not in {"success", "error"}
                or cached.get(row.isbn, {}).get("deferred", False)
            ]
            if not pending:
                state["completed_at"] = datetime.now(KST).isoformat()
                state.pop("next_run_at", None)
                save_json(state_path, state)
                metrics = summarize(rows, root, state)
                print(f"Completed: 500/500 attempted; success {metrics['status_counts'].get('success', 0)}", flush=True)
                return
            eligible = [row for row in pending if row.isbn not in state["attempted_today"]]
            allowance = max(0, (args.daily_call_budget - state["d4l_requests"]) // 3)
            batch = eligible[:min(allowance, args.max_books)]
            if state["paused_day"] == today:
                batch = []
            for row in batch:
                if state["d4l_requests"] + 3 > args.daily_call_budget:
                    break
                state["attempted_today"].append(row.isbn)
                save_json(state_path, state)
                for attempt in range(2):
                    upstream_errors.clear()
                    quota_errors.clear()
                    d4l_responses.clear()
                    capture: dict = {}
                    item = await _generate_one(client, sem, row.isbn, capture=capture)
                    item["generated_at"] = datetime.now(KST).isoformat()
                    item["d4l_responses"] = list(d4l_responses)
                    incomplete = bool(upstream_errors) or len(d4l_responses) != 3
                    if incomplete:
                        item = {"isbn": row.isbn, "status": "error", "error_code": "d4l_incomplete",
                                "d4l_responses": list(d4l_responses), "generated_at": item["generated_at"],
                                "deferred": bool(quota_errors) or state["d4l_requests"] + 3 > args.daily_call_budget}
                    save_json(root / "attempts" / row.isbn / f"{datetime.now(KST):%Y%m%dT%H%M%S%f}.json", item)
                    if quota_errors:
                        state["paused_day"] = today
                        break
                    if not incomplete or attempt == 1 or item["deferred"]:
                        break
                    print(f"Transient D4L failure; retrying {row.isbn} after 2 seconds", flush=True)
                    await asyncio.sleep(2)
                if "llm_input" in capture:
                    # 같은 책을 다른 생성 조건으로 다시 돌릴 때 외부 API를 또 쓰지 않도록
                    # LLM에 넣은 입력을 그대로 보관한다. 두 실행의 입력이 같아야 비교가 성립한다.
                    save_json(root / "inputs" / f"{row.isbn}.json",
                              {"isbn": row.isbn, "captured_at": item["generated_at"], **capture})
                if item["status"] == "success":
                    _assert_published_evidence_key(row.isbn, item["result"]["fields"])
                    request = ValidateRequest.model_validate({"fields": item["result"]["fields"]})
                    item["validation"] = validate_marc_fields(request.fields)
                save_json(root / "results" / f"{row.isbn}.json", item)
                save_json(state_path, state)
                metrics = summarize(rows, root, state)
                print(f"Processed {metrics['processed']}/500; success {metrics['status_counts'].get('success', 0)}; "
                      f"D4L requests {state['d4l_requests']}; latest {row.isbn}: {item['status']}", flush=True)
                if state["paused_day"] == today:
                    break
                await asyncio.sleep(1)
            metrics = summarize(rows, root, state)
            if metrics["processed"] == len(rows) and not any(
                item.get("deferred", False) for item in bulk.load_cached_results(root / "results").values()
            ):
                continue
            if args.once:
                return
            # Do not hammer failures within the same day or silently run without D4L.
            wake = (datetime.now(KST) + timedelta(days=1)).replace(hour=0, minute=10, second=0, microsecond=0)
            state["next_run_at"] = wake.isoformat()
            save_json(state_path, state)
            summarize(rows, root, state)
            print(f"Waiting until {wake.isoformat()}; success {metrics['status_counts'].get('success', 0)}/500", flush=True)
            await asyncio.sleep(max(1, (wake - datetime.now(KST)).total_seconds()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--isbn-csv", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--daily-call-budget", type=int, default=450)
    parser.add_argument("--initial-used-calls", type=int, default=0,
                        help="Today's D4L calls used outside this runner, including dataset collection")
    parser.add_argument("--max-books", type=int, default=150)
    parser.add_argument("--once", action="store_true", help="Run today's batch and exit without waiting")
    args = parser.parse_args()
    if args.max_books < 1 or args.initial_used_calls < 0:
        parser.error("max-books must be positive and initial-used-calls nonnegative")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()

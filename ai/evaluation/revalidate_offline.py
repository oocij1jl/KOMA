"""저장된 생성 결과에 현재 output_validator를 다시 적용한다(후처리 재생).

LLM·외부 API를 호출하지 않는다. 결과 JSON에서 LLM이 만든 필드만 떼어
validate_output에 다시 넣고, 규칙 레이어 필드(generated_by=rule)는 그대로 둔다.
biblio/evidence는 **생성 당시 저장해 둔 LLMInputPayload 스냅샷**에서 그대로
읽는다. 결과 필드에서 표제·출판사를 거꾸로 복원하거나 evidence를 비워 두고
재검증하지 않는다. 근거가 없으면 041/546 같은 근거 의존 필드가 통째로 빠져
"생성이 나빠졌다"는 잘못된 결론이 나오기 때문이다.

스냅샷이 없거나, 스키마가 맞지 않거나, 결과와 다른 책이면 **아무 파일도 쓰지
않고 중단한다.** 스냅샷을 추정해서 만들어 내지 않는다.

한계: --in-dir의 결과는 이미 생성 당시 검증기를 통과한 뒤 저장된 값이다.
그때 제거된 필드는 이 스크립트로 되살아나지 않는다. 따라서 여기서 나오는
수치는 "같은 LLM 출력이 지금 검증기를 지나면 무엇이 더 빠지는가"만 보여주는
후처리 재생(postfilter replay)이며, 새 모델/새 생성으로 다시 만든 점수가 아니다.

    python3 ai/evaluation/revalidate_offline.py \
        --in-dir ai/evaluation/runs/after-rag/results \
        --inputs-dir ai/evaluation/runs/after-rag/inputs \
        --out-dir ai/evaluation/runs/after-rag-revalidated/results
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.schemas.llm import LLMInputPayload  # noqa: E402
from backend.services.marc_generator import _enforce_generation_tags  # noqa: E402
from backend.services.output_validator import validate_output  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover
    from backend.schemas.llm import LLMInputPayload as LLMInputPayloadType


class SnapshotError(ValueError):
    """생성 시점 LLMInputPayload 스냅샷을 믿고 쓸 수 없을 때 사용한다."""


def load_llm_input(inputs_dir: Path, isbn: str) -> "LLMInputPayloadType":
    """<ISBN>.json 스냅샷을 생성 당시 스키마 그대로 읽는다."""

    path = inputs_dir / f"{isbn}.json"
    if not path.is_file():
        raise SnapshotError(f"생성 시점 LLM 입력 스냅샷 없음: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"LLM 입력 스냅샷 JSON 파싱 실패: {path}: {exc.msg}") from exc
    try:
        llm_input = LLMInputPayload.model_validate(raw)
    except ValidationError as exc:
        raise SnapshotError(f"LLM 입력 스냅샷이 LLMInputPayload 스키마와 다름: {path}: {exc}") from exc
    if llm_input.isbn != isbn:
        raise SnapshotError(f"스냅샷 isbn({llm_input.isbn})이 결과 파일 이름({isbn})과 다름: {path}")
    return llm_input


def check_identity(payload: dict[str, Any], llm_input: "LLMInputPayloadType", source: str) -> None:
    """결과에 전사된 020 ISBN과 스냅샷이 같은 책인지 확인한다."""

    transcribed = {
        str(subfield.get("value", ""))
        for field in payload.get("fields", [])
        if isinstance(field, dict) and field.get("tag") == "020"
        for subfield in field.get("subfields", [])
        if isinstance(subfield, dict) and subfield.get("code") == "a" and subfield.get("value")
    }
    if not transcribed:
        return
    if llm_input.isbn in transcribed or (llm_input.biblio.isbn_ea and llm_input.biblio.isbn_ea in transcribed):
        return
    raise SnapshotError(
        f"스냅샷 isbn({llm_input.isbn})이 결과의 020 ISBN({sorted(transcribed)})과 다른 책이다: {source}"
    )


def field_key(field: dict[str, Any]) -> str:
    return json.dumps(
        {key: field.get(key) for key in ("tag", "indicator1", "indicator2", "subfields")},
        ensure_ascii=False,
        sort_keys=True,
    )


def revalidate(
    payload: dict[str, Any], *, llm_input: "LLMInputPayloadType"
) -> tuple[dict[str, Any], list[str], list[str]]:
    """저장된 결과의 LLM 필드만 현재 검증기로 다시 거른다.

    llm_input은 생성 당시 실제로 LLM에 들어간 입력 봉투여야 한다. 이 함수는
    biblio/evidence를 어떤 식으로도 복원하거나 추정하지 않는다.
    """
    check_identity(payload, llm_input, "재검증 결과")

    fields = payload.get("fields", [])
    rule_fields = [field for field in fields if field.get("generated_by") == "rule"]
    llm_fields = [field for field in fields if field.get("generated_by") != "rule"]

    raw_output = json.dumps({"fields": llm_fields, "skipped_fields": [], "warnings": []}, ensure_ascii=False)
    result = validate_output(raw_output, biblio=llm_input.biblio, evidence=llm_input.evidence)
    _enforce_generation_tags(result, llm_input)
    kept = [field.model_dump(mode="json", by_alias=True) for field in result.fields]

    before = Counter(field_key(field) for field in llm_fields)
    after = Counter(field_key(field) for field in kept)
    changed = [json.loads(key)["tag"] for key in (after - before).elements()]
    replaced = Counter(json.loads(key)["tag"] for key in (before - after).elements())
    removed = list((replaced - Counter(changed)).elements())

    known_skips = {item.get("tag") for item in payload.get("skipped_fields", []) if isinstance(item, dict)}
    skipped = list(payload.get("skipped_fields", [])) + [
        item.model_dump(mode="json", by_alias=True) for item in result.skipped_fields if item.tag in removed and item.tag not in known_skips
    ]
    warnings = list(payload.get("warnings", [])) + [warning for warning in result.warnings if warning not in payload.get("warnings", [])]
    return {"fields": rule_fields + kept, "skipped_fields": skipped, "warnings": warnings}, removed, changed


def load_batch(in_dir: Path, inputs_dir: Path) -> list[tuple[Path, dict[str, Any], "LLMInputPayloadType"]]:
    """결과와 스냅샷을 모두 짝지어 읽는다. 하나라도 어긋나면 중단한다."""

    batch: list[tuple[Path, dict[str, Any], "LLMInputPayloadType"]] = []
    problems: list[str] = []
    for path in sorted(in_dir.glob("*.json")):
        if path.name.endswith(".error.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"결과 JSON 파싱 실패: {path}: {exc.msg}")
            continue
        try:
            llm_input = load_llm_input(inputs_dir, path.stem)
            check_identity(payload, llm_input, str(path))
        except SnapshotError as exc:
            problems.append(str(exc))
            continue
        batch.append((path, payload, llm_input))

    if problems:
        raise SnapshotError(
            f"LLM 입력 스냅샷 {len(problems)}건이 유효하지 않아 재검증을 중단한다. 결과 파일을 하나도 쓰지 않았다.\n"
            + "\n".join(f"- {problem}" for problem in problems)
        )
    if not batch:
        raise SnapshotError(f"재검증할 결과 JSON이 없다: {in_dir}")
    return batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--in-dir", type=Path, required=True, help="저장된 생성 결과 <ISBN>.json 디렉터리")
    parser.add_argument(
        "--inputs-dir",
        type=Path,
        required=True,
        help="생성 당시 LLMInputPayload 스냅샷 <ISBN>.json 디렉터리 (필수, 대체 추정 없음)",
    )
    parser.add_argument("--out-dir", type=Path, required=True, help="재검증 결과를 쓸 디렉터리 (--in-dir와 달라야 한다)")
    args = parser.parse_args()

    if not args.in_dir.is_dir():
        parser.error(f"--in-dir 디렉터리가 없다: {args.in_dir}")
    if not args.inputs_dir.is_dir():
        parser.error(f"--inputs-dir 디렉터리가 없다: {args.inputs_dir}")
    if args.out_dir.resolve() in {args.in_dir.resolve(), args.inputs_dir.resolve()}:
        parser.error("--out-dir는 --in-dir 또는 --inputs-dir와 같을 수 없다. 원본을 덮어쓴다.")

    try:
        batch = load_batch(args.in_dir, args.inputs_dir)
    except SnapshotError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc

    removed_total: Counter[str] = Counter()
    outputs: list[tuple[str, dict[str, Any]]] = []
    for path, payload, llm_input in batch:
        new_payload, removed, changed = revalidate(payload, llm_input=llm_input)
        removed_total.update(removed)
        if removed or changed:
            print(f"{path.stem}: 제거 {removed or '-'} / 값 변경 {changed or '-'}")
        outputs.append((path.name, new_payload))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, new_payload in outputs:
        (args.out_dir / name).write_text(json.dumps(new_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"재검증 {len(outputs)}건 (후처리 재생, 재생성 점수 아님)")
    print(f"제거된 필드: {dict(removed_total)}")


if __name__ == "__main__":
    main()

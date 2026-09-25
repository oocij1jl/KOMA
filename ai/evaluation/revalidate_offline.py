"""저장된 생성 결과에 현재 output_validator를 다시 적용한다.

LLM·외부 API를 호출하지 않는다. 결과 JSON에서 LLM이 만든 필드만 떼어
validate_output에 다시 넣고, 규칙 레이어 필드(generated_by=rule)는 그대로 둔다.
biblio는 규칙 레이어가 만든 245/260에서 표제·출판사를 되살린다.

검증기 규칙이 바뀐 뒤 "같은 LLM 출력이었다면 최종 결과가 어떻게 달라지는가"를
보는 용도다. 실제 재생성을 대신하지 않는다. 필드 제거 외의 변화가 생기면
그대로 출력해 확인할 수 있게 한다.

    python3 ai/evaluation/revalidate_offline.py \
        --in-dir ai/evaluation/runs/after-rag/results \
        --out-dir ai/evaluation/runs/after-rag-revalidated/results
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from backend.schemas.lookup import BiblioSchema  # noqa: E402
from backend.services.output_validator import validate_output  # noqa: E402


def first_value(fields: list[dict[str, Any]], tag: str, code: str) -> str:
    for field in fields:
        if field.get("tag") != tag:
            continue
        for subfield in field.get("subfields", []):
            if subfield.get("code") == code and subfield.get("value"):
                return str(subfield["value"])
    return ""


def rebuild_biblio(fields: list[dict[str, Any]]) -> BiblioSchema:
    title = first_value(fields, "245", "a")
    subtitle = first_value(fields, "245", "b")
    return BiblioSchema(
        found=True,
        title=f"{title} : {subtitle}" if subtitle else title,
        publisher=first_value(fields, "260", "b"),
    )


def field_key(field: dict[str, Any]) -> str:
    return json.dumps({"tag": field.get("tag"), "subfields": field.get("subfields")}, ensure_ascii=False, sort_keys=True)


def revalidate(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
    fields = payload.get("fields", [])
    rule_fields = [field for field in fields if field.get("generated_by") == "rule"]
    llm_fields = [field for field in fields if field.get("generated_by") != "rule"]

    raw_output = json.dumps({"fields": llm_fields, "skipped_fields": [], "warnings": []}, ensure_ascii=False)
    result = validate_output(raw_output, biblio=rebuild_biblio(rule_fields), evidence=None)
    kept = [field.model_dump(mode="json", by_alias=True) for field in result.fields]

    before = Counter(field_key(field) for field in llm_fields)
    after = Counter(field_key(field) for field in kept)
    removed = [json.loads(key)["tag"] for key in (before - after).elements()]
    changed = [json.loads(key)["tag"] for key in (after - before).elements()]

    known_skips = {item.get("tag") for item in payload.get("skipped_fields", []) if isinstance(item, dict)}
    skipped = list(payload.get("skipped_fields", [])) + [
        item.model_dump(mode="json", by_alias=True) for item in result.skipped_fields if item.tag in removed and item.tag not in known_skips
    ]
    warnings = list(payload.get("warnings", [])) + [warning for warning in result.warnings if warning not in payload.get("warnings", [])]
    return {"fields": rule_fields + kept, "skipped_fields": skipped, "warnings": warnings}, removed, changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--in-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    removed_total: Counter[str] = Counter()
    for path in sorted(args.in_dir.glob("*.json")):
        if path.name.endswith(".error.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        new_payload, removed, changed = revalidate(payload)
        removed_total.update(removed)
        if removed or changed:
            print(f"{path.stem}: 제거 {removed or '-'} / 값 변경 {changed or '-'}")
        (args.out_dir / path.name).write_text(json.dumps(new_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"제거된 필드: {dict(removed_total)}")


if __name__ == "__main__":
    main()

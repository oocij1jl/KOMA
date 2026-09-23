"""
/api/export  ─  MARC 내보내기 라우터

편집 화면에서 확정한 필드 목록을 받아 .mrc(MARC21 바이너리) / .mrk(MARC
mnemonic 텍스트) / json 세 형식 중 하나로 내려준다. 서버에는 아무것도
저장하지 않는다 — "저장"은 클라이언트가 이 응답을 파일로 받는 것으로 끝난다.

지시기호/식별기호 모양은 /api/validate의 MarcField를 그대로 재사용한다
(ind1/ind2, indicator1/indicator2 둘 다 받음 — validate.py 참고).
"""

from __future__ import annotations

import importlib
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

try:  # pragma: no cover - import path depends on startup context
    from backend.routers.validate import MarcField
except ModuleNotFoundError:  # pragma: no cover - backend-local execution
    MarcField = importlib.import_module("routers.validate").MarcField

from pymarc import Field as MarcpyField
from pymarc import Leader, Record
from pymarc import Subfield as MarcpySubfield

router = APIRouter()

DEFAULT_LEADER = "00000nam a2200000 a 4500"  # position 9 = 'a' → UTF-8 인코딩


class ExportRequest(BaseModel):
    fields: list[MarcField]
    format: Literal["mrc", "mrk", "json"] = "mrk"


def build_marc_record(fields: list[MarcField]) -> Record:
    record = Record()
    record.leader = Leader(DEFAULT_LEADER)
    for field in fields:
        record.add_field(
            MarcpyField(
                tag=field.tag,
                indicators=[field.ind1, field.ind2],
                subfields=[MarcpySubfield(code=sf.code, value=sf.value) for sf in field.subfields],
            )
        )
    return record


@router.post("/export/marc")
async def export_marc(body: ExportRequest) -> Response:
    if not body.fields:
        raise HTTPException(status_code=422, detail="내보낼 필드가 없습니다.")

    if body.format == "json":
        payload = [field.model_dump() for field in body.fields]
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="koma_export.json"'},
        )

    record = build_marc_record(body.fields)

    if body.format == "mrc":
        return Response(
            content=record.as_marc(),
            media_type="application/marc",
            headers={"Content-Disposition": 'attachment; filename="koma_export.mrc"'},
        )

    # mrk (기본값)
    return Response(
        content=str(record).encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="koma_export.mrk"'},
    )

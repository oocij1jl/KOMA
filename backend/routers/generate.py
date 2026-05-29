"""
/api/generate  ─  LLM 기반 KORMARC 초안 생성 라우터 (구현 예정)

현재: 플레이스홀더. 다음 단계에서 RAG + LLM 호출 구현.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/generate")
async def generate_marc():
    """
    [TODO] 서지 정보 + KORMARC 규칙 RAG → LLM → MARC 초안 JSON 반환

    입력 예정: lookup 결과 biblio 객체
    출력 예정: 필드별 { tag, ind1, ind2, subfields, source, needs_review } 배열
    """
    return {"message": "generate 엔드포인트 구현 예정"}
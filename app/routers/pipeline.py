from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from app.graph.pipeline_graph import pipeline_graph
from app.models.pipeline import PipelineGenerateResponse

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


@router.post(
    "/generate",
    response_model=PipelineGenerateResponse,
    summary="AI 파이프라인 설계",
    description=(
        "PRD PDF와 기획자 요구사항을 입력받아 "
        "LangGraph 기반 다단계 분석으로 프로젝트 파이프라인 아이템 목록을 설계합니다."
    ),
)
async def generate_pipeline(
    requirements: str = Form(
        ...,
        description="기획자 요구사항 텍스트 (필수)",
        example="사용자가 인증 후 피트니스 루틴을 관리하는 서비스",
    ),
    prd_file: Optional[UploadFile] = File(
        None,
        description="PRD PDF 파일 (선택, 없으면 requirements 텍스트만으로 설계)",
    ),
) -> PipelineGenerateResponse:
    # PDF 바이트 읽기
    pdf_bytes: Optional[bytes] = None
    if prd_file is not None:
        if not prd_file.filename.endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="PDF 파일만 업로드 가능합니다.",
            )
        pdf_bytes = await prd_file.read()

    # LangGraph 실행
    try:
        result = await pipeline_graph.ainvoke({
            "requirements": requirements,
            "pdf_bytes": pdf_bytes,
            "parsed_text": "",
            "prd_summary": "",
            "domains": [],
            "raw_items": "",
            "pipeline": [],
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"파이프라인 설계 중 오류가 발생했습니다: {str(e)}",
        )

    pipeline_items = result.get("pipeline", [])

    return PipelineGenerateResponse(
        pipeline=pipeline_items,
        total_count=len(pipeline_items),
    )

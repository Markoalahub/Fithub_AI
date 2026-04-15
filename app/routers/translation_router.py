"""
번역 라우터 — 기획자-개발자 간 AI 번역 API 엔드포인트

엔드포인트:
- POST /meetings/{id}/translate-to-technical    기획자 → 개발자 번역
- POST /meetings/{id}/translate-to-planning      개발자 → 기획자 번역
- POST /meetings/{id}/finalize-translation-session  세션 종료 및 요약
- GET  /meetings/search                          임베딩 검색
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.translation import (
    TranslateToTechnicalRequest,
    TranslateToTechnicalResponse,
    TranslateToPlanningRequest,
    TranslateToPlanningResponse,
    FinalizationResponse,
    TranslationSearchResponse,
    TranslationSearchResult,
)
from app.services import translation_service

router = APIRouter(prefix="/meetings", tags=["translation"])


@router.post(
    "/{meeting_id}/translate-to-technical",
    response_model=TranslateToTechnicalResponse,
    summary="기획자 → 개발자 번역",
    description="기획자의 질문/요구사항을 개발자가 이해하는 기술적 언어로 번역",
)
async def translate_to_technical(
    meeting_id: int,
    request: TranslateToTechnicalRequest,
    db: AsyncSession = Depends(get_db),
) -> TranslateToTechnicalResponse:
    """
    기획자의 질문을 개발자 언어로 번역

    예시:
    ```json
    {
      "original_statement": "사용자가 이전에 본 상품을 추천해주는 기능을 만들 수 있나?",
      "context": "전자상거래 플랫폼"
    }
    ```

    응답에는 다음이 포함됩니다:
    - problem_statement: 기술 용어로 표현한 문제
    - technical_approach: 구현 방식 (배열)
    - tech_stack: 필요 기술들
    - effort_estimate: 예상 개발 기간
    - dependencies: 선행 작업 사항
    """
    try:
        # 번역 수행
        ai_translation = await translation_service.translate_to_technical(
            request.original_statement,
            request.context,
        )

        # 번역 결과 저장
        await translation_service.save_translation_message(
            db,
            meeting_id,
            role="planner",
            original=request.original_statement,
            ai_translation=ai_translation.dict(),
            target_audience="developer",
        )

        await db.commit()

        return TranslateToTechnicalResponse(
            meeting_id=meeting_id,
            original_statement=request.original_statement,
            ai_translation=ai_translation,
            saved_at=translation_service.datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{meeting_id}/translate-to-planning",
    response_model=TranslateToPlanningResponse,
    summary="개발자 → 기획자 번역",
    description="개발자의 기술적 설명을 기획자가 이해하는 비즈니스 언어로 번역",
)
async def translate_to_planning(
    meeting_id: int,
    request: TranslateToPlanningRequest,
    db: AsyncSession = Depends(get_db),
) -> TranslateToPlanningResponse:
    """
    개발자의 기술적 설명을 기획자 언어로 번역

    예시:
    ```json
    {
      "developer_statement": "지금 N+1 쿼리 문제가 있어서 fetch join이나 batch_size를 조정해야 해",
      "context": "성능 최적화"
    }
    ```

    응답에는 다음이 포함됩니다:
    - simple_explanation: 한 문장 요약
    - analogy: 실생활 비유
    - impact: 비즈니스 영향도
    - timeline: 소요 시간
    - why_needed: 필요 이유 (기획자 관점)
    """
    try:
        # 번역 수행
        ai_translation = await translation_service.translate_to_planning(
            request.developer_statement,
            request.context,
        )

        # 번역 결과 저장
        await translation_service.save_translation_message(
            db,
            meeting_id,
            role="developer",
            original=request.developer_statement,
            ai_translation=ai_translation.dict(),
            target_audience="planner",
        )

        await db.commit()

        return TranslateToPlanningResponse(
            meeting_id=meeting_id,
            original_statement=request.developer_statement,
            ai_translation=ai_translation,
            saved_at=translation_service.datetime.utcnow(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/{meeting_id}/finalize-translation-session",
    response_model=FinalizationResponse,
    summary="번역 세션 종료 및 요약",
    description="대화 세션을 종료하고 전체 내용을 요약하여 임베딩 생성 및 저장",
)
async def finalize_translation_session(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
) -> FinalizationResponse:
    """
    번역 세션 종료

    처리 내용:
    1. 전체 번역 대화 요약 생성
    2. 요약 텍스트 임베딩 생성
    3. 세션 상태를 'completed'로 업데이트
    4. DB에 저장

    반환값:
    - session_summary: 전체 요약 (마크다운 형식)
    - embedding_id: 생성된 임베딩 ID
    - session_status: "completed"
    """
    try:
        result = await translation_service.finalize_translation_session(
            db,
            meeting_id,
            session_note=None,
        )

        return FinalizationResponse(
            meeting_id=result["meeting_id"],
            session_summary=result["session_summary"],
            key_agreements=[],  # 향후 파싱으로 추출
            next_steps=[],  # 향후 파싱으로 추출
            embedding_id=result["embedding_id"],
            session_status=result["session_status"],
            saved_at=translation_service.datetime.fromisoformat(
                result["created_at"]
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/search",
    response_model=TranslationSearchResponse,
    summary="번역 세션 검색",
    description="임베딩 기반 번역 세션 검색 (향후 pgvector 활용)",
)
async def search_translations(
    query: str = Query(..., min_length=2, description="검색 쿼리"),
    limit: int = Query(10, ge=1, le=100, description="최대 결과 수"),
    db: AsyncSession = Depends(get_db),
) -> TranslationSearchResponse:
    """
    번역 세션 검색

    현재는 텍스트 검색으로 구현되어 있으며, 나중에 pgvector를 사용한
    의미론적 검색(semantic search)으로 업그레이드 예정

    예시: GET /meetings/search?query=사용자%20추천&limit=5
    """
    try:
        import time

        start_time = time.time()

        results = await translation_service.search_translations(
            db,
            query,
            limit,
        )

        elapsed_ms = (time.time() - start_time) * 1000

        return TranslationSearchResponse(
            query=query,
            total_results=len(results),
            results=[
                TranslationSearchResult(
                    meeting_id=r["meeting_id"],
                    summary=r["summary"],
                    session_date=translation_service.datetime.fromisoformat(
                        r["session_date"]
                    ),
                    relevance_score=r.get("relevance_score", 0.85),
                    conversation_type=r["conversation_type"],
                )
                for r in results
            ],
            search_time_ms=elapsed_ms,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{meeting_id}/translation-history",
    summary="번역 이력 조회",
    description="특정 번역 세션의 전체 대화 이력 조회",
)
async def get_translation_history(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    번역 세션의 전체 대화 이력 조회

    반환값:
    ```json
    {
      "messages": [
        {
          "role": "planner" | "developer",
          "original": "원본 텍스트",
          "ai_translation": {...},
          "target_audience": "developer" | "planner",
          "timestamp": "2026-04-15T10:30:00"
        },
        ...
      ]
    }
    ```
    """
    try:
        history = await translation_service.get_translation_history(
            db, meeting_id
        )

        if history is None:
            raise HTTPException(
                status_code=404,
                detail="번역 이력을 찾을 수 없습니다.",
            )

        return history

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

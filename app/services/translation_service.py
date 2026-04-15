"""
Translation Service — 기획자-개발자 간 AI 번역

기능:
- 기획자 질문 → 개발자 기술 언어로 번역
- 개발자 설명 → 기획자 언어로 번역
- 번역 대화 저장
- 세션 종료 시 요약 및 임베딩 생성
- 임베딩 기반 검색
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
import math

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.config import get_settings
from app.models.db.meeting import MeetingLog
from app.schemas.translation import (
    TechnicalTranslation,
    PlanningTranslation,
    TranslationMessage,
)


def _get_llm() -> ChatOpenAI:
    """GPT-4o mini LLM 인스턴스 (저비용 고성능)"""
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )


def _get_embeddings() -> OpenAIEmbeddings:
    """OpenAI Embeddings 인스턴스"""
    settings = get_settings()
    return OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=settings.openai_api_key,
    )


def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """두 벡터 간 코사인 유사도 계산 (0.0 ~ 1.0)"""
    if not vec1 or not vec2:
        return 0.0

    # 내적 계산
    dot_product = sum(a * b for a, b in zip(vec1, vec2))

    # 각 벡터의 크기 계산
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)


# ──────────────────────────────────────────────
# 번역 함수들
# ──────────────────────────────────────────────


async def translate_to_technical(
    original_statement: str,
    context: Optional[str] = None,
) -> TechnicalTranslation:
    """
    기획자의 질문/요구사항을 개발자가 이해하는 기술적 언어로 번역
    """
    llm = _get_llm()

    system_prompt = """당신은 시니어 기술 리더입니다. 기획자의 요구사항을 개발자가 명확하게 이해할 수 있도록
기술적 언어로 변환합니다.

다음 항목들을 포함하여 JSON 형식으로 응답하세요:
1. problem_statement - 핵심 문제를 기술 용어로 표현
2. technical_approach - 구체적인 구현 방식 (배열, 3-5개 항목)
3. tech_stack - 필요한 기술들 (배열)
4. effort_estimate - 예상 개발 기간 (예: "3-5일")
5. dependencies - 선행 작업 또는 확인 사항 (배열, 필요시 빈 배열)

반드시 JSON 형식으로만 응답하세요."""

    user_message = f"""기획자의 요구사항:
{original_statement}"""

    if context:
        user_message += f"\n\n컨텍스트:\n{context}"

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ],
        config=RunnableConfig(run_name="번역-기획자→개발자")
    )

    # JSON 파싱
    response_text = response.content
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    try:
        result_dict = json.loads(response_text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="번역 결과 JSON 파싱 실패",
        )

    return TechnicalTranslation(**result_dict)


async def translate_to_planning(
    developer_statement: str,
    context: Optional[str] = None,
) -> PlanningTranslation:
    """
    개발자의 기술적 설명을 기획자가 이해하는 비즈니스 언어로 번역
    """
    llm = _get_llm()

    system_prompt = """당신은 기술 이야기를 기획자도 이해할 수 있는 비즈니스 언어로 변환하는 전문가입니다.

다음 항목들을 포함하여 JSON 형식으로 응답하세요:
1. simple_explanation - 한 문장 요약 (초등학생도 이해할 수 있는 수준)
2. analogy - 실생활 비유 (예: 데이터베이스 = 창고, 쿼리 = 상품 찾기 등)
3. impact - 비즈니스 영향도 (사용자 경험, 비용, 속도 등)
4. timeline - 예상 소요 시간
5. why_needed - 왜 이 작업이 필요한지 (기획자 관점)

반드시 JSON 형식으로만 응답하세요."""

    user_message = f"""개발자의 기술적 설명:
{developer_statement}"""

    if context:
        user_message += f"\n\n컨텍스트:\n{context}"

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ],
        config=RunnableConfig(run_name="번역-개발자→기획자")
    )

    # JSON 파싱
    response_text = response.content
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    try:
        result_dict = json.loads(response_text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="번역 결과 JSON 파싱 실패",
        )

    return PlanningTranslation(**result_dict)


# ──────────────────────────────────────────────
# 번역 저장 및 관리
# ──────────────────────────────────────────────


async def save_translation_message(
    db: AsyncSession,
    meeting_id: int,
    role: str,
    original: str,
    ai_translation: Dict[str, Any],
    target_audience: str,
) -> None:
    """
    번역된 메시지를 MeetingLog.translation_history에 저장
    """
    meeting = await _get_meeting_for_translation(db, meeting_id)

    # translation_history 초기화 또는 업데이트
    if meeting.translation_history is None:
        meeting.translation_history = {"messages": []}

    message = {
        "role": role,
        "original": original,
        "ai_translation": ai_translation,
        "target_audience": target_audience,
        "timestamp": datetime.utcnow().isoformat(),
    }

    meeting.translation_history["messages"].append(message)
    meeting.is_translation_session = True
    meeting.conversation_type = "translation"

    await db.flush()


async def _get_meeting_for_translation(
    db: AsyncSession, meeting_id: int
) -> MeetingLog:
    """번역 세션용 MeetingLog 조회"""
    result = await db.execute(
        select(MeetingLog)
        .options(
            selectinload(MeetingLog.attendees),
            selectinload(MeetingLog.step_relations),
        )
        .where(MeetingLog.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다.")
    return meeting


async def generate_embedding(text: str) -> List[float]:
    """
    텍스트를 OpenAI embeddings API로 임베딩
    """
    embeddings = _get_embeddings()
    return await embeddings.aembed_query(
        text,
        config=RunnableConfig(run_name="회의-임베딩-생성")
    )


async def finalize_translation_session(
    db: AsyncSession,
    meeting_id: int,
    session_note: Optional[str] = None,
) -> Dict[str, Any]:
    """
    번역 세션 종료:
    1. 전체 대화 요약 생성
    2. 임베딩 생성 및 저장
    3. 세션 상태 완료 처리
    """
    meeting = await _get_meeting_for_translation(db, meeting_id)

    # 1. 전체 대화 기반 요약 생성
    session_summary = await _generate_session_summary(
        meeting.translation_history,
        session_note,
    )

    # 2. 임베딩 생성
    try:
        embedding_vector = await generate_embedding(session_summary)
        # 벡터를 JSON 문자열로 저장
        meeting.embedding = json.dumps(embedding_vector)
        embedding_id = f"vec_{meeting_id}_{datetime.utcnow().timestamp()}"
    except Exception as e:
        print(f"임베딩 생성 실패: {e}")
        embedding_id = None

    # 3. 요약 및 상태 저장
    meeting.summary = session_summary
    meeting.session_status = "completed"

    await db.flush()
    await db.commit()

    return {
        "meeting_id": meeting_id,
        "session_summary": session_summary,
        "embedding_id": embedding_id,
        "session_status": "completed",
        "created_at": datetime.utcnow().isoformat(),
    }


async def _generate_session_summary(
    translation_history: Optional[Dict[str, Any]],
    session_note: Optional[str] = None,
) -> str:
    """
    번역 세션의 전체 대화를 요약
    """
    if not translation_history or not translation_history.get("messages"):
        return "번역 대화 기록 없음"

    llm = _get_llm()

    # 대화 이력 포맷팅
    conversation_text = "\n\n".join(
        [
            f"[{msg['role'].upper()}] {msg['original']}\n"
            f"→ [AI 번역] {json.dumps(msg['ai_translation'], ensure_ascii=False, indent=2)}"
            for msg in translation_history.get("messages", [])
        ]
    )

    system_prompt = """당신은 기획자와 개발자 간 번역 대화를 종합하는 전문가입니다.

다음 번역 대화를 종합하여 마크다운 형식의 요약을 작성하세요:

## 기획자 요구사항
- 주요 내용 (2-3줄)

## 기술적 해석
- 기술 접근 방식 (2-3줄)
- 필요 기술 스택

## 합의 사항
- 예상 개발 기간
- 필수 작업 항목

## 다음 단계
- 액션 아이템 (3-5개)

간결하고 명확하게 작성하세요."""

    user_message = f"""번역 대화:

{conversation_text}

{f"세션 노트: {session_note}" if session_note else ""}

위 대화를 종합하여 요약하세요."""

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ],
        config=RunnableConfig(run_name="convert_meeting")
    )

    return response.content


# ──────────────────────────────────────────────
# 검색 및 조회
# ──────────────────────────────────────────────


async def search_translations(
    db: AsyncSession,
    query: str,
    limit: int = 10,
    similarity_threshold: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    임베딩 기반 번역 세션 검색

    메모리 기반 코사인 유사도로 계산합니다.
    """
    # 쿼리 임베딩 생성
    try:
        query_embedding = await generate_embedding(query)
    except Exception as e:
        print(f"쿼리 임베딩 생성 실패: {e}")
        return []

    # DB에서 모든 completed 번역 세션 조회
    result = await db.execute(
        select(MeetingLog)
        .where(
            and_(
                MeetingLog.session_status == "completed",
                MeetingLog.is_translation_session == True,
                MeetingLog.embedding != None,  # 임베딩이 있어야 함
            )
        )
        .order_by(MeetingLog.created_at.desc())
        .limit(100)  # 최대 100개 중에서 유사도 계산
    )

    meetings = result.scalars().all()

    if not meetings:
        return []

    # 각 회의의 유사도 계산
    scored_results = []
    for meeting in meetings:
        try:
            # 저장된 임베딩 파싱
            meeting_embedding = json.loads(meeting.embedding)

            # 코사인 유사도 계산
            similarity = _cosine_similarity(query_embedding, meeting_embedding)

            if similarity >= similarity_threshold:
                scored_results.append({
                    "meeting_id": meeting.id,
                    "summary": meeting.summary[:200] if meeting.summary else "요약 없음",
                    "session_date": meeting.created_at.isoformat(),
                    "relevance_score": round(similarity, 3),
                    "conversation_type": meeting.conversation_type,
                })
        except (json.JSONDecodeError, TypeError):
            # 임베딩 파싱 실패 시 스킵
            continue

    # 유사도 점수로 정렬
    scored_results.sort(key=lambda x: x["relevance_score"], reverse=True)

    return scored_results[:limit]


async def _fallback_text_search(
    db: AsyncSession,
    query: str,
    limit: int,
) -> List[Dict[str, Any]]:
    """
    임시: 텍스트 기반 검색 (pgvector 미사용)
    요약(summary) 필드에서 쿼리 문자열을 포함하는 기록 검색
    """
    result = await db.execute(
        select(MeetingLog)
        .where(
            and_(
                MeetingLog.session_status == "completed",
                MeetingLog.is_translation_session == True,
                MeetingLog.summary.contains(query),  # 텍스트 검색
            )
        )
        .order_by(MeetingLog.created_at.desc())
        .limit(limit)
    )

    meetings = result.scalars().all()

    return [
        {
            "meeting_id": m.id,
            "summary": m.summary[:200] if m.summary else "요약 없음",
            "session_date": m.created_at.isoformat(),
            "conversation_type": m.conversation_type,
            "relevance_score": 0.85,  # 임시 점수
        }
        for m in meetings
    ]


async def get_translation_history(
    db: AsyncSession,
    meeting_id: int,
) -> Optional[Dict[str, Any]]:
    """
    특정 번역 세션의 전체 대화 이력 조회
    """
    meeting = await _get_meeting_for_translation(db, meeting_id)
    return meeting.translation_history

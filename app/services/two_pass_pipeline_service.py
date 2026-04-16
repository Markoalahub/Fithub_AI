"""
2-Pass AI 파이프라인 생성 시스템

Pass 1 (Planner): PDF 분석 → PipelineDirection 도출
Pass 2 (Builder): Direction 병렬 처리 → PipelineStepCreate 생성
"""

import json
import asyncio
import logging
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.config import get_settings
from app.schemas.two_pass_pipeline import PipelineDirection, PlannerResponse
from app.schemas.pipeline import PipelineStepCreate, PipelineCreate

logger = logging.getLogger(__name__)


def _get_planner_llm() -> ChatOpenAI:
    """Pass 1용 대형 LLM (gpt-4o)"""
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )


def _get_builder_llm() -> ChatOpenAI:
    """Pass 2용 경량 LLM (gpt-4o-mini)"""
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )


def _parse_json_response(response_text: str) -> dict:
    """
    LLM 응답에서 JSON을 추출하여 파싱
    마크다운 코드블록 제거 후 JSON 파싱
    """
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.error(f"JSON 파싱 실패: {response_text[:100]}")
        raise ValueError(f"JSON 파싱 실패: {e}")


# ──────────────────────────────────────────────
# Pass 1: Planner
# ──────────────────────────────────────────────


async def planner_pass(pdf_text: str) -> PlannerResponse:
    """
    Pass 1: PDF 텍스트를 분석하여 파이프라인 방향성(Direction) 도출

    Args:
        pdf_text: Docling으로 파싱된 PDF 마크다운 텍스트

    Returns:
        PlannerResponse: Direction 리스트와 프로젝트 요약

    Raises:
        ValueError: JSON 파싱 실패
    """
    llm = _get_planner_llm()

    system_prompt = """당신은 시니어 소프트웨어 아키텍트입니다.
주어진 PDF 콘텐츠를 분석하여 개발 파이프라인의 큰 방향성만 설계하세요.

각 Direction은:
- 독립적인 하나의 파이프라인 흐름 (한 직군 담당)
- 명확한 목표와 우선순위를 가짐
- 구체적인 기술스택 힌트를 포함

중요: 세부 구현 스텝이나 체크리스트는 작성하지 마세요!
오직 방향성과 목표만 정의하세요.

반드시 다음 JSON 형식으로만 응답하세요:
{
  "directions": [
    {
      "category": "BE|FE|AI|DEVOPS|QA|...",
      "goal": "파이프라인 목표 (1~2문장)",
      "priority": 1,
      "tech_hint": "기술스택 힌트",
      "estimated_steps": 5
    }
  ],
  "project_summary": "프로젝트 전체 요약"
}
"""

    user_message = f"""다음 PDF 콘텐츠를 분석하고 파이프라인 방향성을 설계하세요:

---PDF 콘텐츠---
{pdf_text}

---
위 내용을 기반으로 JSON 형식의 파이프라인 방향성을 생성하세요."""

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ],
        config=RunnableConfig(run_name="두패스-Planner"),
    )

    # JSON 파싱
    result_dict = _parse_json_response(response.content)

    # PlannerResponse 검증
    try:
        return PlannerResponse(
            directions=[
                PipelineDirection(**d) for d in result_dict.get("directions", [])
            ],
            total_count=len(result_dict.get("directions", [])),
            project_summary=result_dict.get(
                "project_summary", "프로젝트 요약을 추출할 수 없습니다."
            ),
        )
    except Exception as e:
        logger.error(f"PlannerResponse 생성 실패: {e}")
        raise ValueError(f"PlannerResponse 검증 실패: {e}")


# ──────────────────────────────────────────────
# Pass 2: Builder
# ──────────────────────────────────────────────


async def builder_pass(direction: PipelineDirection) -> List[PipelineStepCreate]:
    """
    Pass 2: 각 Direction을 받아 구체적인 PipelineStep 생성

    Args:
        direction: Pass 1에서 도출된 파이프라인 방향성

    Returns:
        List[PipelineStepCreate]: 생성된 파이프라인 스텝 목록

    Raises:
        ValueError: JSON 파싱 실패
    """
    llm = _get_builder_llm()

    system_prompt = """당신은 개발 태스크를 세분화하는 전문가입니다.
주어진 파이프라인 방향성(Direction)을 보고 구체적인 구현 스텝을 생성하세요.

각 스텝은:
- 구체적인 액션을 설명 (동사로 시작)
- 명확한 설명과 4~6개의 상세 항목 포함
- 예상 소요 시간 명시
- 필요한 기술스택 포함
- origin은 항상 "ai_generated"

정확히 {estimated_steps}개의 스텝을 생성하세요.

반드시 다음 JSON 형식의 배열로만 응답하세요:
[
  {
    "step_task_description": "구체적 액션 제목과 상세 설명",
    "step_sequence_number": 1,
    "duration": "예상 기간 (예: '2-3일')",
    "tech_stack": "필요한 기술 (예: 'Spring Boot 3.x, JPA')",
    "origin": "ai_generated"
  }
]
"""

    user_message = f"""다음 파이프라인 방향성을 기반으로 구체적인 구현 스텝을 생성하세요:

카테고리: {direction.category}
목표: {direction.goal}
기술스택 힌트: {direction.tech_hint}
예상 스텝 개수: {direction.estimated_steps}개

정확히 {direction.estimated_steps}개의 PipelineStepCreate를 JSON 배열로 생성하세요.
- step_task_description: 구체적인 작업 상세 내용 (제목 + 설명)
- step_sequence_number: 1부터 시작하는 순서 번호
- duration: 예상 소요 시간
- tech_stack: 필요한 기술스택
- origin: "ai_generated" 고정"""

    response = llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ],
        config=RunnableConfig(run_name="두패스-Builder"),
    )

    # JSON 파싱
    result_list = _parse_json_response(response.content)

    if not isinstance(result_list, list):
        logger.error(f"Builder 응답이 배열이 아님: {type(result_list)}")
        raise ValueError("Builder 응답은 배열 형식이어야 합니다.")

    # PipelineStepCreate 검증
    try:
        steps = []
        for idx, item in enumerate(result_list, start=1):
            # step_sequence_number 자동 할당
            item["step_sequence_number"] = idx
            step = PipelineStepCreate(**item)
            steps.append(step)

        logger.info(
            f"Builder 완료: {direction.category} - {len(steps)}개 스텝 생성"
        )
        return steps
    except Exception as e:
        logger.error(f"PipelineStepCreate 생성 실패: {e}")
        raise ValueError(f"스텝 검증 실패: {e}")


# ──────────────────────────────────────────────
# Orchestration
# ──────────────────────────────────────────────


async def generate_pipeline_from_pdf(
    project_id: int,
    pdf_text: str,
    category: Optional[str] = None,
) -> List[PipelineCreate]:
    """
    2-Pass 파이프라인 생성 시스템의 메인 오케스트레이션 함수

    Args:
        project_id: Spring DB의 프로젝트 ID
        pdf_text: Docling으로 파싱된 PDF 마크다운 텍스트
        category: 특정 직군만 처리 (예: "BE") - None이면 모든 방향성 처리

    Returns:
        List[PipelineCreate]: 생성된 파이프라인 목록 (DB 저장 준비 완료)

    Process:
        1. Pass 1: PDF 분석 → PipelineDirection 리스트 도출
        2. Pass 2: 각 Direction을 asyncio.gather로 병렬 처리 → PipelineStepCreate 생성
        3. PipelineCreate 목록으로 조립
    """
    logger.info(f"2-Pass 파이프라인 생성 시작: project_id={project_id}")

    # Step 1: Planner 실행
    logger.info("Pass 1 (Planner) 실행 중...")
    try:
        planner_response = await planner_pass(pdf_text)
        logger.info(
            f"Pass 1 완료: {planner_response.total_count}개 Direction 도출"
        )
    except Exception as e:
        logger.error(f"Pass 1 실패: {e}")
        raise

    # 필터링 (category 지정 시)
    directions = planner_response.directions
    if category:
        directions = [d for d in directions if d.category.upper() == category.upper()]
        logger.info(f"카테고리 필터링: {len(directions)}개 Direction")

    if not directions:
        logger.warning("처리할 Direction이 없습니다.")
        return []

    # Step 2: Builder 병렬 실행
    logger.info(f"Pass 2 (Builder) 병렬 실행 중... ({len(directions)}개 Direction)")
    try:
        all_steps = await asyncio.gather(
            *[builder_pass(direction) for direction in directions],
            return_exceptions=True,
        )
        logger.info("Pass 2 완료: 모든 Direction 처리됨")
    except Exception as e:
        logger.error(f"Pass 2 실패: {e}")
        raise

    # Step 3: PipelineCreate 목록 조립
    pipelines = []
    for direction, steps in zip(directions, all_steps):
        # 개별 Builder 실패 처리
        if isinstance(steps, Exception):
            logger.warning(
                f"Direction {direction.category} 처리 실패: {steps}, 스킵"
            )
            continue

        pipeline = PipelineCreate(
            project_id=project_id,
            category=direction.category,
            version=1,
            is_active="Active",
            steps=steps,
        )
        pipelines.append(pipeline)
        logger.info(f"파이프라인 생성: {direction.category} ({len(steps)}개 스텝)")

    logger.info(f"2-Pass 파이프라인 생성 완료: {len(pipelines)}개 파이프라인")
    return pipelines

"""
다중 직군 파이프라인 생성 (FE, BE, DevOps, AI)

Workflow:
  1. parse_pdf           — PDF 파싱
  2. understand_prd      — 전체 PRD 요약 (한 번)
  3. generate_all_categories — 모든 직군에 대해 병렬 처리
     ├─ [FE] understand → identify_domains → generate_items → prioritize
     ├─ [BE] understand → identify_domains → generate_items → prioritize
     ├─ [DevOps] understand → identify_domains → generate_items → prioritize
     └─ [AI] understand → identify_domains → generate_items → prioritize
  4. combine_pipelines   — 모든 파이프라인 통합
"""

import json
import tempfile
import os
from typing import TypedDict, Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from docling.document_converter import DocumentConverter

from app.models.pipeline import PipelineItem
from app.config import get_settings
from app.templates.backend_templates import (
    SPRING_BOOT_TEMPLATE,
    REACT_TEMPLATE,
    DEVOPS_TEMPLATE,
    AI_ENGINEER_TEMPLATE,
)


# ──────────────────────────────────────────────
# 직군별 역할 정의
# ──────────────────────────────────────────────

CATEGORY_ROLE_MAP = {
    "FE": (
        "프론트엔드 개발자",
        "React 기반 UI 구현, 컴포넌트 설계, API 연동, 상태 관리, "
        "라우팅, 반응형 디자인, 성능 최적화"
    ),
    "BE": (
        "백엔드 개발자",
        "REST API 설계 및 구현, DB 스키마 설계, 비즈니스 로직, 인증/인가(JWT), "
        "캐싱, 테스트 코드 작성, 성능 튜닝"
    ),
    "DEVOPS": (
        "DevOps 엔지니어",
        "CI/CD 파이프라인, 컨테이너화(Docker/K8s), 클라우드 인프라, "
        "모니터링, 로그 수집, 보안 설정"
    ),
    "AI": (
        "AI/ML 엔지니어",
        "데이터 수집·전처리, 모델 학습·평가, 추론 API 서빙, "
        "벡터 DB, RAG 파이프라인, MLOps"
    ),
}

TEMPLATE_MAP = {
    "FE": REACT_TEMPLATE,
    "BE": SPRING_BOOT_TEMPLATE,
    "DEVOPS": DEVOPS_TEMPLATE,
    "AI": AI_ENGINEER_TEMPLATE,
}

DEFAULT_CATEGORIES = ["BE", "FE"]  # 기본: 백엔드, 프론트엔드


# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

class MultiCategoryPipelineState(TypedDict):
    requirements: str                          # 기획자 요구사항 텍스트
    pdf_bytes: Optional[bytes]                 # 업로드된 PDF 바이트
    categories: List[str]                      # 생성할 직군 목록 (기본: ["BE", "FE"])
    parsed_text: str                           # PDF 파싱 결과
    global_prd_summary: str                    # 전체 PRD 요약
    pipelines: Dict[str, Dict]                 # {직군: {phases: [...], items: [...]}}


# ──────────────────────────────────────────────
# LLM 초기화
# ──────────────────────────────────────────────

def _get_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model="gpt-4o",
        temperature=0.3,
        api_key=settings.openai_api_key,
    )


# ──────────────────────────────────────────────
# Node 1: PDF 파싱
# ──────────────────────────────────────────────

def parse_pdf(state: MultiCategoryPipelineState) -> MultiCategoryPipelineState:
    """Docling으로 PRD PDF 파싱"""
    pdf_bytes = state.get("pdf_bytes")

    if not pdf_bytes:
        return {**state, "parsed_text": ""}

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        converter = DocumentConverter()
        result = converter.convert(tmp_path)
        parsed_text = result.document.export_to_markdown()
    finally:
        os.unlink(tmp_path)

    return {**state, "parsed_text": parsed_text}


# ──────────────────────────────────────────────
# Node 2: 전체 PRD 요약 (한 번만)
# ──────────────────────────────────────────────

def understand_prd_global(state: MultiCategoryPipelineState) -> MultiCategoryPipelineState:
    """전체 PRD를 프로젝트 관점에서 요약"""
    llm = _get_llm()

    prd_content = ""
    if state.get("parsed_text"):
        prd_content += f"## PRD 문서\n{state['parsed_text']}\n\n"
    if state.get("requirements"):
        prd_content += f"## 기획자 요구사항\n{state['requirements']}"

    messages = [
        SystemMessage(content=(
            "당신은 경험 많은 PM(Product Manager)입니다. "
            "PRD(Product Requirements Document)를 분석하여 프로젝트 전체의 핵심 목표, "
            "주요 기능, 기술 요구사항, 그리고 각 직군(FE/BE/DevOps/AI)과의 연동 포인트를 요약하세요."
        )),
        HumanMessage(content=(
            f"{prd_content}\n\n"
            "다음을 요약해주세요:\n"
            "1. 프로젝트의 핵심 목표 (1-2문장)\n"
            "2. 주요 기능 영역 (기능별로)\n"
            "3. 사용할 주요 기술 스택 (프론트: React, 백엔드: Spring 등)\n"
            "4. FE/BE/DevOps/AI 각 직군이 담당할 영역\n"
            "5. 직군 간 중요한 연동 포인트"
        )),
    ]

    response = llm.invoke(messages)
    return {**state, "global_prd_summary": response.content}


# ──────────────────────────────────────────────
# Node 3: 직군별 파이프라인 생성 (병렬 처리)
# ──────────────────────────────────────────────

def _generate_category_pipeline(
    category: str,
    global_summary: str,
    requirements: str,
    parsed_text: str,
) -> tuple[str, Dict]:
    """단일 직군의 파이프라인 생성"""
    llm = _get_llm()
    role_name, role_desc = CATEGORY_ROLE_MAP.get(category, ("개발자", ""))
    template = TEMPLATE_MAP.get(category)

    prd_content = ""
    if parsed_text:
        prd_content += f"## PRD 문서\n{parsed_text}\n\n"
    if requirements:
        prd_content += f"## 기획자 요구사항\n{requirements}\n\n"

    # 1단계: 직군 관점의 요구사항 분석
    understand_msg = [
        SystemMessage(content=(
            f"당신은 시니어 {role_name}입니다. "
            f"역할: {role_desc}\n"
            f"전체 프로젝트 분석:\n{global_summary}\n\n"
            f"이를 바탕으로 당신의 직군({category})이 구현해야 할 구체적인 요구사항을 분석하세요."
        )),
        HumanMessage(content=(
            f"{prd_content}\n"
            f"{role_name}({category})이 개발해야 할 구체적인 요구사항은 무엇인가요?"
        )),
    ]

    understand_response = llm.invoke(understand_msg)
    category_summary = understand_response.content

    # 2단계: 개발 아이템 생성
    details_guide = {
        "FE": "- 페이지/컴포넌트명\n- API 연동 방식\n- 상태 관리 전략",
        "BE": "- API 엔드포인트\n- DB 테이블\n- 비즈니스 로직",
        "DEVOPS": "- 인프라 구성\n- CI/CD 단계\n- 모니터링 대상",
        "AI": "- 데이터 소스\n- 모델 타입\n- 평가 지표",
    }.get(category, "- 구체적인 구현 방법")

    items_msg = [
        SystemMessage(content=(
            f"당신은 10년 경력의 시니어 {role_name}입니다.\n"
            f"역할: {role_desc}\n\n"
            "PRD 분석 결과를 바탕으로 즉시 개발에 착수할 수 있는 수준의 "
            "구체적인 파이프라인 아이템을 5~10개 생성하세요."
        )),
        HumanMessage(content=(
            f"## 분석 결과\n{category_summary}\n\n"
            f"## 개발 가이드\n{details_guide}\n\n"
            "**JSON 형식으로만 응답하세요:**\n"
            """[
  {
    "title": "구현할 기능명",
    "priority": 1,
    "details": [
      "구체적인 구현 사항 1",
      "구체적인 구현 사항 2",
      "완료 기준"
    ]
  }
]"""
        )),
    ]

    items_response = llm.invoke(items_msg)

    # JSON 파싱
    content = items_response.content.strip()
    if "```" in content:
        content = content.split("```")[1].lstrip("json\n")

    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        items = []

    # 템플릿과 함께 반환
    return category, {
        "template": template,
        "summary": category_summary,
        "items": items,
    }


def generate_all_categories(state: MultiCategoryPipelineState) -> MultiCategoryPipelineState:
    """모든 직군의 파이프라인을 병렬로 생성"""
    categories = state.get("categories", DEFAULT_CATEGORIES)
    global_summary = state.get("global_prd_summary", "")
    requirements = state.get("requirements", "")
    parsed_text = state.get("parsed_text", "")

    pipelines = {}

    # 병렬 처리
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                _generate_category_pipeline,
                category,
                global_summary,
                requirements,
                parsed_text,
            )
            for category in categories
        ]

        for future in futures:
            category, pipeline_data = future.result()
            pipelines[category] = pipeline_data

    return {**state, "pipelines": pipelines}


# ──────────────────────────────────────────────
# Node 4: 파이프라인 통합
# ──────────────────────────────────────────────

def combine_pipelines(state: MultiCategoryPipelineState) -> MultiCategoryPipelineState:
    """모든 직군의 파이프라인을 최종 형식으로 통합"""
    pipelines = state.get("pipelines", {})

    # 이미 combine된 상태라면 그대로 반환
    return state


# ──────────────────────────────────────────────
# Graph 구성
# ──────────────────────────────────────────────

def build_multi_category_pipeline_graph():
    """다중 직군 파이프라인 생성 그래프"""
    graph = StateGraph(MultiCategoryPipelineState)

    # 노드 추가
    graph.add_node("parse_pdf", parse_pdf)
    graph.add_node("understand_prd_global", understand_prd_global)
    graph.add_node("generate_all_categories", generate_all_categories)
    graph.add_node("combine_pipelines", combine_pipelines)

    # 엣지 추가
    graph.set_entry_point("parse_pdf")
    graph.add_edge("parse_pdf", "understand_prd_global")
    graph.add_edge("understand_prd_global", "generate_all_categories")
    graph.add_edge("generate_all_categories", "combine_pipelines")
    graph.add_edge("combine_pipelines", END)

    return graph.compile()

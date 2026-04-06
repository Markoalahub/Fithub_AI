"""
LangGraph-based AI Pipeline Design Workflow

Nodes:
  1. parse_pdf       — Docling으로 PRD PDF 파싱
  2. understand_prd  — GPT-4o로 PRD 목적/범위/핵심 요구사항 요약
  3. identify_domains — 프로젝트 도메인 영역 식별
  4. generate_items  — 파이프라인 아이템 및 세부 구현사항 생성
  5. prioritize      — 우선순위 정렬 (HIGH / MEDIUM / LOW)
"""
import json
import tempfile
import os
from typing import TypedDict, Optional, List

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from docling.document_converter import DocumentConverter

from app.models.pipeline import PipelineItem, Priority
from app.config import get_settings


# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

class PipelineState(TypedDict):
    requirements: str            # 기획자 요구사항 텍스트
    pdf_bytes: Optional[bytes]   # 업로드된 PDF 원본 바이트
    parsed_text: str             # Docling 파싱 결과
    prd_summary: str             # PRD 이해/요약 결과
    domains: List[str]           # 식별된 도메인 영역
    raw_items: str               # LLM이 생성한 JSON 문자열
    pipeline: List[PipelineItem] # 최종 파이프라인 아이템 목록


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
# Node 1: PDF 파싱 (Docling)
# ──────────────────────────────────────────────

def parse_pdf(state: PipelineState) -> PipelineState:
    """Docling으로 PRD PDF를 파싱하여 구조화된 텍스트 추출"""
    pdf_bytes = state.get("pdf_bytes")

    if not pdf_bytes:
        # PDF 없이 요구사항 텍스트만 있는 경우
        return {**state, "parsed_text": ""}

    # 임시 파일로 저장 후 Docling 변환
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
# Node 2: PRD 이해 (GPT-4o)
# ──────────────────────────────────────────────

def understand_prd(state: PipelineState) -> PipelineState:
    """GPT-4o로 PRD 전체 목적·범위·핵심 요구사항 요약"""
    llm = _get_llm()

    prd_content = ""
    if state.get("parsed_text"):
        prd_content += f"## PRD 문서 내용\n{state['parsed_text']}\n\n"
    if state.get("requirements"):
        prd_content += f"## 기획자 추가 요구사항\n{state['requirements']}"

    messages = [
        SystemMessage(content=(
            "당신은 시니어 소프트웨어 아키텍트입니다. "
            "PRD(Product Requirements Document)를 분석하여 "
            "프로젝트의 핵심 목적, 범위, 주요 기능 요구사항을 명확하게 요약하세요. "
            "요약은 이후 파이프라인 설계에 사용됩니다."
        )),
        HumanMessage(content=(
            f"{prd_content}\n\n"
            "위 PRD를 분석하여 다음을 요약해주세요:\n"
            "1. 프로젝트의 핵심 목적 (1-2문장)\n"
            "2. 주요 기능 영역\n"
            "3. 비기능 요구사항 (성능, 보안, 확장성 등)\n"
            "4. 명시적으로 제외된 범위 (있다면)"
        )),
    ]

    response = llm.invoke(messages)
    return {**state, "prd_summary": response.content}


# ──────────────────────────────────────────────
# Node 3: 도메인 영역 식별 (GPT-4o)
# ──────────────────────────────────────────────

def identify_domains(state: PipelineState) -> PipelineState:
    """PRD에서 프로젝트 도메인 영역 식별 (예: 인증, 결제, 알림 등)"""
    llm = _get_llm()

    messages = [
        SystemMessage(content=(
            "당신은 시니어 소프트웨어 아키텍트입니다. "
            "PRD 분석 결과를 바탕으로 구현에 필요한 핵심 도메인 영역을 식별하세요. "
            "각 도메인은 독립적으로 개발 가능한 단위여야 합니다."
        )),
        HumanMessage(content=(
            f"## PRD 분석 결과\n{state['prd_summary']}\n\n"
            f"## 원본 요구사항\n{state.get('requirements', '')}\n\n"
            "위 PRD에서 개발이 필요한 핵심 도메인 영역을 식별해주세요. "
            "JSON 배열 형식으로만 응답하세요. 예시:\n"
            '["사용자 인증", "프로필 관리", "데이터 분석", "알림 시스템"]'
        )),
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    # JSON 파싱 (코드블록 제거)
    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        domains = json.loads(content)
        if not isinstance(domains, list):
            domains = [content]
    except json.JSONDecodeError:
        # 파싱 실패 시 텍스트에서 추출
        domains = [line.strip().lstrip("-•").strip()
                   for line in content.splitlines()
                   if line.strip() and not line.startswith("[")]

    return {**state, "domains": domains}


# ──────────────────────────────────────────────
# Node 4: 파이프라인 아이템 생성 (GPT-4o)
# ──────────────────────────────────────────────

def generate_items(state: PipelineState) -> PipelineState:
    """각 도메인별 파이프라인 아이템 및 세부 구현사항 생성"""
    llm = _get_llm()

    domains_str = "\n".join(f"- {d}" for d in state.get("domains", []))

    messages = [
        SystemMessage(content=(
            "당신은 시니어 소프트웨어 아키텍트입니다. "
            "식별된 도메인 영역을 바탕으로 구체적인 파이프라인 아이템을 설계하세요. "
            "각 아이템은 명확한 제목, 목적 설명, 그리고 개발자가 바로 착수할 수 있는 "
            "세부 구현사항 목록을 포함해야 합니다."
        )),
        HumanMessage(content=(
            f"## PRD 분석 결과\n{state['prd_summary']}\n\n"
            f"## 식별된 도메인 영역\n{domains_str}\n\n"
            f"## 원본 요구사항\n{state.get('requirements', '')}\n\n"
            "위 도메인들을 바탕으로 파이프라인 아이템 목록을 생성해주세요.\n"
            "반드시 아래 JSON 형식으로만 응답하세요:\n"
            """[
  {
    "title": "파이프라인 아이템 제목",
    "content": "이 아이템의 목적과 핵심 내용 (2-3문장)",
    "priority": "HIGH",
    "details": [
      "세부 구현사항 1",
      "세부 구현사항 2",
      "세부 구현사항 3"
    ]
  }
]"""
            "\n\npriority는 반드시 HIGH, MEDIUM, LOW 중 하나여야 합니다. "
            "세부 구현사항은 각 아이템당 3-5개를 작성하세요."
        )),
    ]

    response = llm.invoke(messages)
    return {**state, "raw_items": response.content}


# ──────────────────────────────────────────────
# Node 5: 우선순위 정렬 및 검증
# ──────────────────────────────────────────────

def prioritize(state: PipelineState) -> PipelineState:
    """파이프라인 아이템 파싱, 검증, 우선순위 정렬"""
    raw = state.get("raw_items", "")

    # 코드블록 제거
    content = raw.strip()
    if "```" in content:
        parts = content.split("```")
        # json 블록 추출
        for part in parts:
            stripped = part.strip()
            if stripped.startswith("json"):
                content = stripped[4:].strip()
                break
            elif stripped.startswith("[") or stripped.startswith("{"):
                content = stripped
                break

    try:
        raw_list = json.loads(content)
    except json.JSONDecodeError:
        # 파싱 실패 시 LLM으로 재정제
        llm = _get_llm()
        fix_messages = [
            SystemMessage(content="JSON 형식 수정 전문가입니다. 주어진 텍스트에서 유효한 JSON 배열을 추출하세요."),
            HumanMessage(content=f"다음 텍스트에서 JSON 배열만 추출하여 응답하세요:\n\n{raw}"),
        ]
        fix_response = llm.invoke(fix_messages)
        raw_list = json.loads(fix_response.content.strip())

    # Pydantic 모델로 변환 및 검증
    items: List[PipelineItem] = []
    for item in raw_list:
        # priority 정규화
        priority_str = str(item.get("priority", "MEDIUM")).upper()
        if priority_str not in ("HIGH", "MEDIUM", "LOW"):
            priority_str = "MEDIUM"

        items.append(PipelineItem(
            title=item.get("title", ""),
            content=item.get("content", ""),
            priority=Priority(priority_str),
            details=item.get("details", []),
        ))

    # 우선순위 순서로 정렬: HIGH → MEDIUM → LOW
    priority_order = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}
    items.sort(key=lambda x: priority_order[x.priority])

    return {**state, "pipeline": items}


# ──────────────────────────────────────────────
# 그래프 빌드
# ──────────────────────────────────────────────

def build_pipeline_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("parse_pdf", parse_pdf)
    graph.add_node("understand_prd", understand_prd)
    graph.add_node("identify_domains", identify_domains)
    graph.add_node("generate_items", generate_items)
    graph.add_node("prioritize", prioritize)

    graph.set_entry_point("parse_pdf")
    graph.add_edge("parse_pdf", "understand_prd")
    graph.add_edge("understand_prd", "identify_domains")
    graph.add_edge("identify_domains", "generate_items")
    graph.add_edge("generate_items", "prioritize")
    graph.add_edge("prioritize", END)

    return graph.compile()


# 싱글톤 그래프 인스턴스
pipeline_graph = build_pipeline_graph()

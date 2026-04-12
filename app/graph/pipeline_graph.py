"""
LangGraph-based AI Pipeline Design Workflow

Nodes:
  1. parse_pdf       — Docling으로 PRD PDF 파싱
  2. understand_prd  — GPT-4o로 PRD 목적/범위/핵심 요구사항 요약
  3. identify_domains — 직군(category) 관점에서 담당 도메인 식별
  4. generate_items  — 직군별 구체적 태스크 생성 (구현 단위 수준)
  5. prioritize      — 우선순위 정렬 (숫자 오름차순)
"""
import json
import tempfile
import os
from typing import TypedDict, Optional, List

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from docling.document_converter import DocumentConverter

from app.models.pipeline import PipelineItem
from app.config import get_settings


# ──────────────────────────────────────────────
# 직군별 역할 정의
# ──────────────────────────────────────────────

CATEGORY_ROLE_MAP = {
    "FE": (
        "프론트엔드 개발자",
        "React/Next.js 기반 UI 구현, 컴포넌트 설계, API 연동, 상태 관리(Zustand/Redux), "
        "라우팅, 반응형 디자인, 접근성(A11y), 성능 최적화(코드 스플리팅, 이미지 최적화)"
    ),
    "BE": (
        "백엔드 개발자",
        "REST API 설계 및 구현, DB 스키마 설계, 비즈니스 로직, 인증/인가(JWT/OAuth2), "
        "캐싱(Redis), 비동기 처리, 외부 API 연동, 테스트 코드 작성, 성능 튜닝"
    ),
    "AI": (
        "AI/ML 엔지니어",
        "데이터 수집·전처리 파이프라인, 모델 학습·평가, 추론 API 서빙(FastAPI), "
        "벡터 DB(ChromaDB/Pinecone), RAG 파이프라인, LLM 프롬프트 엔지니어링, MLOps"
    ),
    "DEVOPS": (
        "DevOps 엔지니어",
        "CI/CD 파이프라인(GitHub Actions), 컨테이너화(Docker/K8s), 클라우드 인프라(AWS/GCP), "
        "모니터링(Prometheus/Grafana), 로그 수집(ELK), 보안 설정, 오토스케일링"
    ),
    "QA": (
        "QA 엔지니어",
        "테스트 계획 수립, E2E 테스트(Playwright/Cypress), API 테스트(Postman/pytest), "
        "성능 테스트(k6/JMeter), 버그 리포트, 회귀 테스트, 테스트 자동화"
    ),
}

DEFAULT_ROLE = (
    "풀스택 개발자",
    "기능 설계, API 구현, UI 연동, 테스트, 배포"
)


def _get_category_role(category: str) -> tuple[str, str]:
    return CATEGORY_ROLE_MAP.get(category.upper() if category else "", DEFAULT_ROLE)


# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

class PipelineState(TypedDict):
    requirements: str            # 기획자 요구사항 텍스트
    pdf_bytes: Optional[bytes]   # 업로드된 PDF 원본 바이트
    category: str                # 직군 (FE, BE, AI 등)
    parsed_text: str             # Docling 파싱 결과
    prd_summary: str             # PRD 이해/요약 결과
    domains: List[str]           # 직군이 담당할 도메인 영역
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
# Node 2: PRD 이해 (GPT-4o)
# ──────────────────────────────────────────────

def understand_prd(state: PipelineState) -> PipelineState:
    """GPT-4o로 PRD 전체 목적·범위·핵심 요구사항 요약"""
    llm = _get_llm()
    category = state.get("category", "")
    role_name, role_desc = _get_category_role(category)

    prd_content = ""
    if state.get("parsed_text"):
        prd_content += f"## PRD 문서 내용\n{state['parsed_text']}\n\n"
    if state.get("requirements"):
        prd_content += f"## 기획자 추가 요구사항\n{state['requirements']}"

    messages = [
        SystemMessage(content=(
            f"당신은 시니어 {role_name}입니다. "
            "PRD(Product Requirements Document)를 분석하여 "
            f"{role_name} 관점에서 핵심 구현 목표, 기술 범위, 주요 기능 요구사항을 요약하세요. "
            "요약은 이후 구체적인 개발 태스크 설계에 사용됩니다."
        )),
        HumanMessage(content=(
            f"{prd_content}\n\n"
            f"위 PRD를 {role_name} 관점에서 분석하여 다음을 요약해주세요:\n"
            "1. 프로젝트의 핵심 목적 (1-2문장)\n"
            f"2. {role_name}이 담당해야 할 주요 기능 영역\n"
            "3. 기술적 제약사항 및 비기능 요구사항\n"
            "4. 다른 직군(FE/BE/AI)과의 연동 포인트"
        )),
    ]

    response = llm.invoke(messages)
    return {**state, "prd_summary": response.content}


# ──────────────────────────────────────────────
# Node 3: 담당 도메인 식별 (직군 특화)
# ──────────────────────────────────────────────

def identify_domains(state: PipelineState) -> PipelineState:
    """직군(category) 관점에서 담당할 도메인 영역 식별"""
    llm = _get_llm()
    category = state.get("category", "")
    role_name, role_desc = _get_category_role(category)

    messages = [
        SystemMessage(content=(
            f"당신은 시니어 {role_name}입니다. "
            f"{role_name}의 업무 범위: {role_desc}\n"
            "PRD 분석 결과를 바탕으로 이 직군이 담당해야 할 핵심 개발 도메인을 식별하세요. "
            "각 도메인은 독립적으로 개발 가능한 단위여야 합니다."
        )),
        HumanMessage(content=(
            f"## PRD 분석 결과\n{state['prd_summary']}\n\n"
            f"## 원본 요구사항\n{state.get('requirements', '')}\n\n"
            f"{role_name}이 개발해야 할 핵심 도메인 영역을 식별해주세요. "
            "JSON 배열 형식으로만 응답하세요. 예시 (BE의 경우):\n"
            '["사용자 인증 API", "운동 기록 CRUD API", "소셜 피드 API", "알림 서비스"]'
        )),
    ]

    response = llm.invoke(messages)
    content = response.content.strip()

    if "```" in content:
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    try:
        domains = json.loads(content)
        if not isinstance(domains, list):
            domains = [content]
    except json.JSONDecodeError:
        domains = [line.strip().lstrip("-•").strip()
                   for line in content.splitlines()
                   if line.strip() and not line.startswith("[")]

    return {**state, "domains": domains}


# ──────────────────────────────────────────────
# Node 4: 직군별 구체적 파이프라인 아이템 생성
# ──────────────────────────────────────────────

def generate_items(state: PipelineState) -> PipelineState:
    """직군에 맞는 구현 단위 수준의 파이프라인 태스크 생성"""
    llm = _get_llm()
    category = state.get("category", "")
    role_name, role_desc = _get_category_role(category)
    domains_str = "\n".join(f"- {d}" for d in state.get("domains", []))

    # 직군별 details 작성 가이드
    details_guide = {
        "FE": (
            "- 구현할 컴포넌트명과 props 구조\n"
            "- 사용할 라이브러리/훅 (예: useQuery, useForm)\n"
            "- API 연동 방식 (엔드포인트, request/response 구조)\n"
            "- 상태 관리 방법 (전역/로컬)\n"
            "- UI/UX 고려사항 (로딩, 에러, 빈 상태 처리)"
        ),
        "BE": (
            "- API 엔드포인트 (메서드 + URL)\n"
            "- Request/Response DTO 필드\n"
            "- DB 테이블/컬럼 설계\n"
            "- 비즈니스 로직 핵심 처리 흐름\n"
            "- 예외 처리 및 유효성 검사 규칙"
        ),
        "AI": (
            "- 사용 모델/알고리즘\n"
            "- 입력 데이터 형식 및 전처리 방법\n"
            "- 출력 형식 및 후처리 방법\n"
            "- 평가 지표 및 목표 성능\n"
            "- API 서빙 방식 및 응답 스펙"
        ),
    }.get(category.upper() if category else "", (
        "- 구체적인 구현 방법\n"
        "- 사용 기술 스택\n"
        "- 입출력 스펙\n"
        "- 예외 처리 방법\n"
        "- 완료 기준"
    ))

    messages = [
        SystemMessage(content=(
            f"당신은 10년 경력의 시니어 {role_name}입니다.\n"
            f"업무 범위: {role_desc}\n\n"
            "PRD와 담당 도메인을 바탕으로 즉시 개발에 착수할 수 있는 수준의 "
            "구체적인 파이프라인 태스크를 설계하세요.\n"
            "각 태스크의 세부 구현사항은 주니어 개발자가 읽고 바로 구현할 수 있을 만큼 "
            "명확하고 기술적으로 상세해야 합니다."
        )),
        HumanMessage(content=(
            f"## PRD 분석 결과\n{state['prd_summary']}\n\n"
            f"## {role_name} 담당 도메인\n{domains_str}\n\n"
            f"## 원본 요구사항\n{state.get('requirements', '')}\n\n"
            f"위 내용을 바탕으로 {role_name}의 파이프라인 태스크를 생성하세요.\n\n"
            "**세부 구현사항 작성 가이드:**\n"
            f"{details_guide}\n\n"
            "**반드시 아래 JSON 형식으로만 응답하세요:**\n"
            """[
  {
    "title": "태스크 제목 (동사로 시작, 예: '사용자 로그인 API 구현')",
    "priority": 1,
    "details": [
      "구체적인 구현 사항 1 (기술 스펙 포함)",
      "구체적인 구현 사항 2",
      "구체적인 구현 사항 3",
      "구체적인 구현 사항 4",
      "완료 기준 또는 테스트 방법"
    ]
  }
]"""
            "\n\n"
            "규칙:\n"
            "- priority는 개발 의존성을 고려한 순서 (1부터 시작, 선행 태스크가 낮은 번호)\n"
            "- 태스크 수: 5~10개 (너무 크면 분리, 너무 작으면 합치기)\n"
            "- details는 각 태스크당 4~6개, 모두 기술적으로 구체적으로 작성\n"
            "- 태스크 제목에 직군명(FE/BE 등)을 포함하지 말 것"
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

    content = raw.strip()
    if "```" in content:
        parts = content.split("```")
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
        llm = _get_llm()
        fix_messages = [
            SystemMessage(content="JSON 형식 수정 전문가입니다. 주어진 텍스트에서 유효한 JSON 배열을 추출하세요."),
            HumanMessage(content=f"다음 텍스트에서 JSON 배열만 추출하여 응답하세요:\n\n{raw}"),
        ]
        fix_response = llm.invoke(fix_messages)
        raw_list = json.loads(fix_response.content.strip())

    items: List[PipelineItem] = []
    for item in raw_list:
        try:
            priority_val = int(item.get("priority", 999))
        except (ValueError, TypeError):
            priority_val = 999

        items.append(PipelineItem(
            title=item.get("title", ""),
            priority=priority_val,
            details=item.get("details", []),
        ))

    items.sort(key=lambda x: x.priority)
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

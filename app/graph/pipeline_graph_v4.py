"""
Pipeline Graph V4 — Multi-Agent 전문가 협업 기반 파이프라인 생성 엔진

Workflow:
  parse_document → requirement_refiner → flow_planner → ux_architect
    → [be_specialist ∥ fe_specialist] (병렬) → cross_validator → finalize

Agents:
  1. Flow_Planner   : 인터뷰 → User Flow (Mermaid + JSON)
  2. UX_Architect    : User Flow → ASCII Wireframe + Component Tree
  3. BE_Specialist   : User Flow → BE 이슈 (DB → API → Logic)
  4. FE_Specialist   : User Flow + Wireframe → FE 이슈
"""

import json
import logging
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, END

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════
# Shared State
# ══════════════════════════════════════════════

class PipelineStateV4(TypedDict):
    # ── 입력 ──
    prd_context: str
    technical_stack: str
    category: str
    pdf_bytes: Optional[bytes]

    # ── parse_document 출력 ──
    interview_summary: str
    pdf_content: str

    # ── requirement_refiner 출력 ──
    refined_requirements: str

    # ── flow_planner 출력 ──
    user_flow: Dict[str, Any]
    user_flow_mermaid: str

    # ── ux_architect 출력 ──
    wireframes: List[Dict[str, str]]
    component_tree: List[Dict[str, Any]]

    # ── specialist 출력 ──
    be_steps: List[Dict[str, Any]]
    fe_steps: List[Dict[str, Any]]

    # ── 검증 & 최종 ──
    validation_logs: List[str]
    final_pipeline: List[Dict[str, Any]]


# ══════════════════════════════════════════════
# LLM Helper
# ══════════════════════════════════════════════

def _get_llm(model: str = "gpt-4o-mini") -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=0.15,
        api_key=get_settings().openai_api_key,
    )


def _invoke_json(llm: ChatOpenAI, messages: list) -> Any:
    """LLM 호출 후 JSON 파싱. 실패 시 빈 리스트 반환."""
    resp = llm.invoke(messages)
    content = resp.content.strip()
    # ```json ... ``` 블록 제거
    if content.startswith("```"):
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    try:
        start = content.find("{") if "{" in content and (content.find("{") < content.find("[") if "[" in content else True) else content.find("[")
        end = max(content.rfind("}"), content.rfind("]")) + 1
        return json.loads(content[start:end])
    except Exception as e:
        logger.error(f"JSON 파싱 실패: {e}\n원본: {content[:500]}")
        return []


# ══════════════════════════════════════════════
# Node 1: parse_document (기존 재활용)
# ══════════════════════════════════════════════

def parse_document(state: PipelineStateV4) -> dict:
    """PDF 파싱 + 인터뷰 텍스트 분리"""
    import tempfile, os
    from docling.document_converter import DocumentConverter

    requirements = state.get("prd_context", "")
    pdf_bytes = state.get("pdf_bytes")

    # 인터뷰 섹션 분리
    interview_part = ""
    if "🚀 [Ouroboros 사전 인터뷰 최종 요약]" in requirements:
        parts = requirements.split("🚀 [Ouroboros 사전 인터뷰 최종 요약]")
        interview_part = parts[1].split("📝 [기존 요구사항]")[0].strip() if len(parts) > 1 else ""

    # PDF 파싱
    pdf_content = ""
    if pdf_bytes:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            pdf_content = result.document.export_to_markdown()
            os.unlink(tmp_path)
            logger.info(f"[parse_document] PDF 파싱 성공: {len(pdf_content)}자")
        except Exception as e:
            logger.error(f"[parse_document] PDF 파싱 실패: {e}")

    return {
        "interview_summary": interview_part,
        "pdf_content": pdf_content,
        "pdf_bytes": None,
    }


# ══════════════════════════════════════════════
# Node 2: requirement_refiner (기존 재활용)
# ══════════════════════════════════════════════

def requirement_refiner(state: PipelineStateV4) -> dict:
    """인터뷰 + PDF → 압축된 설계 가이드"""
    llm = _get_llm("gpt-4o-mini")
    interview = state.get("interview_summary", "")
    pdf = state.get("pdf_content", "")
    original = state.get("prd_context", "")

    system = (
        "당신은 요구사항 분석 전문가입니다. 인터뷰 내역과 PDF를 통합하여 "
        "'핵심 설계 가이드'를 작성하세요.\n"
        "1. 인터뷰 내용은 기획자와의 최종 합의이므로 PDF보다 우선합니다.\n"
        "2. 중복 제거, 기술적 제약사항과 핵심 비즈니스 로직 위주로 요약.\n"
        "3. 리스트 형태로 압축하세요."
    )
    user = (
        f"### [인터뷰 합의사항]\n{interview or '없음'}\n\n"
        f"### [PDF 원본]\n{pdf or '없음'}\n\n"
        f"### [기타 요구사항]\n{original}"
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return {"refined_requirements": resp.content}


# ══════════════════════════════════════════════
# Node 3: Flow_Planner (기획자 에이전트)
# ══════════════════════════════════════════════

FLOW_PLANNER_PROMPT = """\
🧠 당신은 **Flow_Planner** — 10년 경력의 시니어 프로덕트 매니저입니다.

## 역할
제공된 요구사항을 분석하여 **논리적으로 완전한 User Flow**를 도출합니다.

## 핵심 지침
1. 사용자가 명시하지 않은 **예외 경로(Exception Path)**를 반드시 식별하여 포함하세요.
   (예: 네트워크 오류, 권한 부족, 입력값 검증 실패, 세션 만료 등)
2. 각 플로우 노드는 명확한 **주체(Actor)**와 **행위(Action)**를 포함해야 합니다.
3. 분기(Decision)는 조건을 명시하세요.

## 출력 형식 (Strict JSON)
```json
{
  "flow_name": "서비스명 User Flow",
  "actors": ["사용자", "시스템", "외부API"],
  "nodes": [
    {
      "id": "N1",
      "type": "start|action|decision|exception|end",
      "actor": "사용자",
      "label": "로그인 페이지 진입",
      "next": ["N2"]
    },
    {
      "id": "N2",
      "type": "decision",
      "actor": "시스템",
      "label": "인증 정보 유효?",
      "condition_true": "N3",
      "condition_false": "N4"
    }
  ],
  "mermaid": "graph TD\\n  N1[로그인 페이지 진입] --> N2{인증 유효?}\\n  N2 -->|Yes| N3[대시보드]\\n  N2 -->|No| N4[에러 표시]"
}
```
JSON 외의 텍스트는 출력하지 마세요.
"""


def flow_planner(state: PipelineStateV4) -> dict:
    llm = _get_llm("gpt-4o-mini")
    refined = state.get("refined_requirements", "")
    tech = state.get("technical_stack", "")

    user_msg = f"기술 스택: {tech}\n\n<REQUIREMENTS>\n{refined}\n</REQUIREMENTS>"
    result = _invoke_json(llm, [
        SystemMessage(content=FLOW_PLANNER_PROMPT),
        HumanMessage(content=user_msg),
    ])

    if isinstance(result, dict):
        mermaid = result.get("mermaid", "")
        return {"user_flow": result, "user_flow_mermaid": mermaid}

    return {"user_flow": {"nodes": []}, "user_flow_mermaid": ""}


# ══════════════════════════════════════════════
# Node 4: UX_Architect (UX 전문가 에이전트)
# ══════════════════════════════════════════════

UX_ARCHITECT_PROMPT = """\
🎨 당신은 **UX_Architect** — UX/UI 리드 디자이너입니다.

## 역할
User Flow의 각 화면(Screen)에 대해 **ASCII Wireframe**과 **UI Component Tree**를 설계합니다.

## 핵심 지침
1. ASCII 아트는 명확한 경계선(`+---+`, `| |`)과 레이블(`[Button]`, `<Input>`)을 사용하세요.
2. FE 개발자가 구조를 **즉시 파악**할 수 있도록 작성하세요.
3. 레이아웃 일관성: 동일한 Navigation, Header 패턴을 유지하세요.
4. 각 화면의 컴포넌트를 트리 구조로 정리하세요.

## 출력 형식 (Strict JSON)
```json
{
  "screens": [
    {
      "screen_id": "S1",
      "screen_name": "로그인 페이지",
      "related_flow_nodes": ["N1", "N2"],
      "ascii_wireframe": "+---------------------------+\\n|       [Logo]              |\\n|  <Email Input>            |\\n|  <Password Input>         |\\n|  [Login Button]           |\\n|  [OAuth - GitHub]         |\\n+---------------------------+",
      "components": [
        {"name": "LoginForm", "type": "container", "children": ["EmailInput", "PasswordInput", "LoginButton"]},
        {"name": "OAuthSection", "type": "container", "children": ["GitHubOAuthButton"]}
      ]
    }
  ]
}
```
JSON 외의 텍스트는 출력하지 마세요.
"""


def ux_architect(state: PipelineStateV4) -> dict:
    llm = _get_llm("gpt-4o-mini")
    user_flow = state.get("user_flow", {})

    user_msg = f"<USER_FLOW>\n{json.dumps(user_flow, ensure_ascii=False, indent=2)}\n</USER_FLOW>"
    result = _invoke_json(llm, [
        SystemMessage(content=UX_ARCHITECT_PROMPT),
        HumanMessage(content=user_msg),
    ])

    screens = result.get("screens", []) if isinstance(result, dict) else result if isinstance(result, list) else []

    wireframes = []
    components = []
    for screen in screens:
        wireframes.append({
            "screen_id": screen.get("screen_id", ""),
            "screen_name": screen.get("screen_name", ""),
            "ascii_wireframe": screen.get("ascii_wireframe", ""),
            "related_flow_nodes": json.dumps(screen.get("related_flow_nodes", [])),
        })
        for comp in screen.get("components", []):
            components.append({
                "screen_id": screen.get("screen_id", ""),
                **comp,
            })

    return {"wireframes": wireframes, "component_tree": components}


# ══════════════════════════════════════════════
# Node 5: BE_Specialist (백엔드 전문가 에이전트)
# ══════════════════════════════════════════════

BE_SPECIALIST_PROMPT = """\
⚙️ 당신은 **BE_Specialist** — 시니어 백엔드 엔지니어입니다.

## 역할
User Flow를 기반으로 **DB 스키마 → API 엔드포인트 → 비즈니스 로직** 순서로 백엔드 이슈를 생성합니다.

## 핵심 지침
1. ⛔ **UI 관련 작업은 절대 포함하지 마세요.** 프론트엔드, 컴포넌트, 스타일링 언급 금지.
2. 각 step은 **1 Step : N Issues** 매핑입니다. `details` 배열의 각 항목이 하나의 GitHub Issue가 됩니다.
3. **5-200-4 규칙** 준수: 파일 5개 이하, 200 LOC, 4시간 이내 작업 단위.
4. 의존성 순서: DB 설계 → API 명세 → 비즈니스 로직 → 테스트
5. `details` 형식: `[태그] 구체적 액션 중심 태스크`
   - 태그: [DB], [API], [Logic], [Auth], [Test], [Config]

## 출력 형식 (Strict JSON Array)
```json
[
  {
    "title": "[회원 인증] OAuth2 기반 사용자 인증 시스템 구축",
    "details": [
      "[DB] User, AuthToken 엔티티 설계 및 Flyway 마이그레이션 스크립트 작성",
      "[API] POST /auth/login OAuth2 콜백 엔드포인트 구현",
      "[Logic] JWT AccessToken/RefreshToken 발급 및 검증 서비스 구현",
      "[Test] 인증 플로우 통합 테스트 작성"
    ],
    "tech_stack": ["Spring Boot", "JPA", "Spring Security"],
    "priority": 1,
    "depends_on": []
  }
]
```
JSON 외의 텍스트는 출력하지 마세요.
"""


def be_specialist(state: PipelineStateV4) -> dict:
    llm = _get_llm("gpt-4o-mini")
    user_flow = state.get("user_flow", {})
    tech = state.get("technical_stack", "Spring Boot, JPA")

    # 입력된 기술 스택(tech)을 반드시 준수하도록 시스템 프롬프트 동적 보강
    system_prompt = BE_SPECIALIST_PROMPT.replace(
        "## 핵심 지침\n",
        f"## 핵심 지침\n6. ⚠️ **기술 스택 준수 지침 (필수)**: 반드시 입력으로 지정된 기술 스택인 **'{tech}'**을 완벽히 반영하여 모든 태스크의 세부 내용(DB 테이블 설계, ORM 사용법, 사용하는 라이브러리/프레임워크 등)과 'tech_stack' 리스트를 출력해야 합니다. 예시의 'Spring Boot, JPA'는 단지 예시일 뿐이므로, 반드시 지정된 기술 스택에 어울리는 최적의 설계(예: FastAPI, Next.js, Node.js 등)를 적용하여 구체적이고 전문적인 태스크를 도출해야 합니다.\n"
    )

    user_msg = (
        f"기술 스택: {tech}\n\n"
        f"<USER_FLOW>\n{json.dumps(user_flow, ensure_ascii=False, indent=2)}\n</USER_FLOW>"
    )
    result = _invoke_json(llm, [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ])

    steps = result if isinstance(result, list) else []
    # 정규화
    normalized = []
    for s in steps:
        details = s.get("details", [])
        if isinstance(details, str):
            details = [details]
        tech_stack = s.get("tech_stack", [])
        if isinstance(tech_stack, str):
            tech_stack = [tech_stack]
        normalized.append({
            "title": s.get("title", "BE 작업"),
            "details": details,
            "category": "BE",
            "priority": s.get("priority", 1),
            "tech_stack": tech_stack,
            "depends_on": s.get("depends_on", []),
        })

    return {"be_steps": normalized}


# ══════════════════════════════════════════════
# Node 6: FE_Specialist (프론트엔드 전문가 에이전트)
# ══════════════════════════════════════════════

FE_SPECIALIST_PROMPT = """\
🖥️ 당신은 **FE_Specialist** — 시니어 프론트엔드 엔지니어입니다.

## 역할
User Flow와 UX Architect의 ASCII Wireframe/Component Tree를 결합하여 프론트엔드 이슈를 생성합니다.

## 핵심 지침
1. **상태 관리 로직**과 **UI 컴포넌트**를 분리하여 이슈화하세요.
2. UX_Architect가 정의한 Component Tree를 기반으로 원자적 태스크를 도출하세요.
3. 각 step은 **1 Step : N Issues** 매핑입니다. `details` 배열의 각 항목이 하나의 GitHub Issue가 됩니다.
4. **5-200-4 규칙** 준수: 파일 5개 이하, 200 LOC, 4시간 이내 작업 단위.
5. `details` 형식: `[태그] 구체적 액션 중심 태스크`
   - 태그: [UI], [State], [API], [Route], [Test], [Style]

## 출력 형식 (Strict JSON Array)
```json
[
  {
    "title": "[로그인 화면] OAuth 인증 UI 및 상태 관리 구현",
    "details": [
      "[UI] ASCII 레이아웃 기반 LoginForm 컴포넌트 개발",
      "[State] 인증 상태(isAuthenticated, user) 전역 Store 설계",
      "[API] POST /auth/login API 연동 및 토큰 저장 로직 구현",
      "[Route] 인증 여부에 따른 Protected Route 가드 구현",
      "[Test] 로그인 성공/실패 시나리오 E2E 테스트 작성"
    ],
    "tech_stack": ["React", "TypeScript", "Zustand"],
    "priority": 1,
    "depends_on": []
  }
]
```
JSON 외의 텍스트는 출력하지 마세요.
"""


def fe_specialist(state: PipelineStateV4) -> dict:
    llm = _get_llm("gpt-4o-mini")
    user_flow = state.get("user_flow", {})
    wireframes = state.get("wireframes", [])
    component_tree = state.get("component_tree", [])
    tech = state.get("technical_stack", "React, TypeScript")

    # 입력된 기술 스택(tech)을 반드시 준수하도록 시스템 프롬프트 동적 보강
    system_prompt = FE_SPECIALIST_PROMPT.replace(
        "## 핵심 지침\n",
        f"## 핵심 지침\n6. ⚠️ **기술 스택 준수 지침 (필수)**: 반드시 입력으로 지정된 기술 스택인 **'{tech}'**을 완벽히 반영하여 모든 태스크의 세부 내용(상태 관리 전역 Store 구성, 사용하는 UI 라이브러리/프레임워크 등)과 'tech_stack' 리스트를 출력해야 합니다. 예시의 'React, TypeScript'는 단지 예시일 뿐이므로, 반드시 지정된 기술 스택에 어울리는 최적의 설계(예: Vue, Next.js, Flutter 등)를 적용하여 구체적이고 전문적인 태스크를 도출해야 합니다.\n"
    )

    user_msg = (
        f"기술 스택: {tech}\n\n"
        f"<USER_FLOW>\n{json.dumps(user_flow, ensure_ascii=False, indent=2)}\n</USER_FLOW>\n\n"
        f"<WIREFRAMES>\n{json.dumps(wireframes, ensure_ascii=False, indent=2)}\n</WIREFRAMES>\n\n"
        f"<COMPONENT_TREE>\n{json.dumps(component_tree, ensure_ascii=False, indent=2)}\n</COMPONENT_TREE>"
    )
    result = _invoke_json(llm, [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_msg),
    ])

    steps = result if isinstance(result, list) else []
    normalized = []
    for s in steps:
        details = s.get("details", [])
        if isinstance(details, str):
            details = [details]
        tech_stack = s.get("tech_stack", [])
        if isinstance(tech_stack, str):
            tech_stack = [tech_stack]
        normalized.append({
            "title": s.get("title", "FE 작업"),
            "details": details,
            "category": "FE",
            "priority": s.get("priority", 1),
            "tech_stack": tech_stack,
            "depends_on": s.get("depends_on", []),
        })

    return {"fe_steps": normalized}


# ══════════════════════════════════════════════
# Node 7: Cross-Validator (교차 검증)
# ══════════════════════════════════════════════

def cross_validator(state: PipelineStateV4) -> dict:
    """BE/FE 파이프라인의 품질 검증 및 중복/누락 체크"""
    be_steps = state.get("be_steps", [])
    fe_steps = state.get("fe_steps", [])
    logs: List[str] = []

    # 1. 중복 제목 제거
    seen_be = set()
    deduped_be = []
    for s in be_steps:
        key = s.get("title", "").lower().strip()
        if key and key not in seen_be:
            seen_be.add(key)
            deduped_be.append(s)
        elif key:
            logs.append(f"[BE 중복 제거] {s.get('title')}")

    seen_fe = set()
    deduped_fe = []
    for s in fe_steps:
        key = s.get("title", "").lower().strip()
        if key and key not in seen_fe:
            seen_fe.add(key)
            deduped_fe.append(s)
        elif key:
            logs.append(f"[FE 중복 제거] {s.get('title')}")

    # 2. BE에 UI 관련 이슈가 섞여있는지 검사
    ui_keywords = {"컴포넌트", "component", "css", "스타일", "style", "ui ", "프론트"}
    for s in deduped_be:
        for d in s.get("details", []):
            if any(kw in d.lower() for kw in ui_keywords):
                logs.append(f"[BE 직군 위반] UI 관련 이슈 발견: {d}")

    # 3. 최소 스텝 수 검증
    if len(deduped_be) < 3:
        logs.append(f"[BE 경고] 스텝 수 부족: {len(deduped_be)}개 (최소 3개 권장)")
    if len(deduped_fe) < 3:
        logs.append(f"[FE 경고] 스텝 수 부족: {len(deduped_fe)}개 (최소 3개 권장)")

    logs.append(f"[검증 완료] BE: {len(deduped_be)}개, FE: {len(deduped_fe)}개 스텝 확인")

    return {
        "be_steps": deduped_be,
        "fe_steps": deduped_fe,
        "validation_logs": logs,
    }


# ══════════════════════════════════════════════
# Node 8: Finalize (최종 병합)
# ══════════════════════════════════════════════

def finalize(state: PipelineStateV4) -> dict:
    """BE + FE 스텝을 하나의 파이프라인으로 병합 (BE → FE 순서)"""
    be = state.get("be_steps", [])
    fe = state.get("fe_steps", [])
    merged = be + fe
    return {"final_pipeline": merged}


# ══════════════════════════════════════════════
# Graph 빌드
# ══════════════════════════════════════════════

def build_pipeline_graph_v4() -> StateGraph:
    graph = StateGraph(PipelineStateV4)

    # 노드 등록
    graph.add_node("parse_document", parse_document)
    graph.add_node("requirement_refiner", requirement_refiner)
    graph.add_node("flow_planner", flow_planner)
    graph.add_node("ux_architect", ux_architect)
    graph.add_node("be_specialist", be_specialist)
    graph.add_node("fe_specialist", fe_specialist)
    graph.add_node("cross_validator", cross_validator)
    graph.add_node("finalize", finalize)

    # 순차 흐름: parse → refiner → planner → ux_architect
    graph.set_entry_point("parse_document")
    graph.add_edge("parse_document", "requirement_refiner")
    graph.add_edge("requirement_refiner", "flow_planner")
    graph.add_edge("flow_planner", "ux_architect")

    # 병렬 분기: ux_architect → [be_specialist, fe_specialist]
    graph.add_edge("ux_architect", "be_specialist")
    graph.add_edge("ux_architect", "fe_specialist")

    # 합류: 둘 다 → cross_validator
    graph.add_edge("be_specialist", "cross_validator")
    graph.add_edge("fe_specialist", "cross_validator")

    # 마무리
    graph.add_edge("cross_validator", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()


pipeline_graph_v4 = build_pipeline_graph_v4()

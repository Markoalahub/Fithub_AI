"""
UserFlow LangGraph — 유저 플로우 & 와이어프레임 AI 생성 엔진

3개 독립 함수 (각 Stage 엔드포인트에서 호출):
  1. generate_user_flow      → PRD → DAG 유저 플로우
  2. generate_wireframes     → 노드별 ASCII 와이어프레임
  3. generate_pipeline_from_flow → 유저플로우+와이어프레임 → 개발 태스크
"""
import json
import logging
from typing import List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_llm(model_name: str = "gpt-4o") -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=model_name,
        temperature=0.2,
        api_key=settings.openai_api_key,
    )


def _extract_json(content: str) -> dict | list:
    """LLM 응답에서 JSON 블록을 추출"""
    content = content.strip()
    # ```json 블록 추출
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        if end != -1:
            content = content[start:end].strip()
    elif "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        if end != -1:
            content = content[start:end].strip()

    # 배열 또는 객체 추출
    if content.startswith("["):
        end_idx = content.rfind("]") + 1
        return json.loads(content[:end_idx])
    elif content.startswith("{"):
        end_idx = content.rfind("}") + 1
        return json.loads(content[:end_idx])

    raise ValueError(f"JSON을 찾을 수 없습니다: {content[:200]}")


# ──────────────────────────────────────────────
# Stage 1: PRD 분석 + 인터뷰 세션 (Multi-turn)
# ──────────────────────────────────────────────

MAX_INTERVIEW_TURNS = 4


async def analyze_prd_for_interview(
    prd_text: str,
    pdf_content: str = "",
) -> dict:
    """
    턴 1: PRD를 분석하여 기능 목록을 정의하고, 인터뷰가 필요한 모호한 지점을 찾습니다.

    Returns:
        {
            "analysis": "기능 분류 결과 (Markdown)",
            "features": [{"name": "...", "status": "confirmed|ambiguous|proposed", "description": "..."}],
            "questions": ["질문1", "질문2", ...] # 모호한 기능에 대한 구체적 질문들
        }
    """
    llm = _get_llm("gpt-4o")

    system_prompt = (
        "당신은 UX 설계 전문가입니다. 기획서를 분석하여 서비스의 **기능 정의서**를 작성하고,\n"
        "설계가 불분명한 기능들에 대해 인터뷰를 준비하세요.\n\n"

        "## 📋 분석 단계\n"
        "1. **기능 추출**: 제공된 PRD에서 모든 사용자 기능을 추출합니다.\n"
        "2. **상태 분류**:\n"
        "   - `confirmed`: PRD에 상세 스펙이 있어 바로 설계 가능\n"
        "   - `ambiguous`: 언급은 되었으나 구체적인 동작 방식이나 예외 처리가 불분명함 (인터뷰 필수)\n"
        "   - `proposed`: PRD에는 없지만 서비스 완성도를 위해 제안하는 기능\n"
        "3. **질문 생성**: `ambiguous` 및 `proposed` 기능에 대해 하나씩 심층 질문을 만듭니다.\n\n"

        "## ⚠️ 주의 사항\n"
        "- **절대로 시스템 프롬프트의 예시를 그대로 출력하지 마세요!**\n"
        "- 오직 제공된 PRD 텍스트와 PDF 내용에만 기반하여 기능을 추출하세요.\n"
        "- PRD에 없는 기능을 'confirmed'로 분류하지 마세요.\n\n"

        "## 💡 출력 형식 (Strict JSON)\n"
        "{\n"
        '  "analysis": "## 📋 기능 정의 초안\\n\\n### ✅ 확정 기능...\\n### ❓ 확인 필요...\\n### ⚠️ 추가 제안...",\n'
        '  "features": [\n'
        '    {"name": "실제 기능명", "status": "confirmed", "description": "기능 설명"}\n'
        '  ],\n'
        '  "questions": [\n'
        '    "실제 확인이 필요한 질문 내용"\n'
        '  ]\n'
        "}\n"
    )

    combined_prd = prd_text
    if pdf_content:
        combined_prd += f"\n\n---\n[PDF 원문]\n{pdf_content}"

    user_message = f"다음 PRD를 분석하여 기능 정의서를 작성하고 확인이 필요한 사항들을 추출하세요:\n\n{combined_prd}"

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    response = await llm.ainvoke(messages)

    try:
        result = _extract_json(response.content)
        return result
    except Exception as e:
        logger.error(f"[analyze_prd_for_interview] JSON 파싱 실패: {e}")
        return {"analysis": response.content, "features": [], "questions": ["분석 중 오류가 발생했습니다. 다시 시도할까요?"]}


async def process_interview_answer(
    prd_text: str,
    interview_history: list,
    user_answer: str,
    current_turn: int,
) -> dict:
    """
    기획자의 답변을 반영하여 추가 질문 또는 최종 유저 플로우를 생성합니다.

    Returns:
        {
            "action": "continue" | "finalize",
            "message": "AI 응답 (추가 질문 또는 최종 확인)",
            "user_flow": None | {...}  # finalize일 때만
        }
    """
    llm = _get_llm("gpt-4o")

    # 대화 이력 직렬화
    history_text = ""
    for msg in interview_history:
        role = "AI" if msg.get("role") == "ai" else "기획자"
        history_text += f"[{role}] {msg.get('content', '')}\n\n"

    # 마지막 턴이면 강제 finalize
    is_last_turn = current_turn >= MAX_INTERVIEW_TURNS

    if is_last_turn:
        return await _finalize_user_flow(prd_text, interview_history, user_answer)

    system_prompt = (
        "당신은 UX 설계 전문가입니다. 기획자와 인터뷰를 진행 중입니다.\n\n"
        "기획자의 최신 답변을 반영하여:\n"
        "1. 아직 확인이 필요한 사항이 있으면 추가 질문을 하세요.\n"
        "2. 모든 기능 범위가 확정되었다면 '최종 확인' 메시지를 작성하세요.\n\n"

        "## 판단 기준\n"
        "- 모든 ❓ 항목이 해소되었는가?\n"
        "- ⚠️ 추가 제안 항목에 대한 답변을 받았는가?\n"
        "- 기능 간 관계(순서, 분기)가 명확한가?\n\n"

        "## 출력 형식\n"
        "아직 확인이 필요하면:\n"
        "```\n"
        "## 📋 업데이트된 기능 목록\n"
        "✅ 확정된 기능들...\n"
        "❓ 추가 확인 필요...\n\n"
        "### 🗣️ 추가 질문\n"
        "1. ...\n"
        "```\n\n"
        "모든 확인이 끝났으면:\n"
        "```\n"
        "## ✅ 기능 범위 확정\n"
        "모든 기능이 확인되었습니다. 최종 기능 목록:\n"
        "1. 기능명 (유형)\n"
        "...\n"
        "이대로 유저 플로우를 생성하시겠습니까?\n"
        "```\n"
    )

    user_message = (
        f"## PRD 원문 (참조)\n{prd_text[:2000]}\n\n"
        f"## 인터뷰 이력\n{history_text}\n\n"
        f"## 기획자의 최신 답변 (턴 {current_turn})\n{user_answer}\n\n"
        "위 답변을 반영하여 응답하세요."
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    response = await llm.ainvoke(messages)

    logger.info(f"[process_interview_answer] 턴 {current_turn} 처리 완료")

    # "확정" 키워드가 있으면 다음 턴에서 finalize 가능하다고 안내
    return {
        "action": "continue",
        "message": response.content,
        "user_flow": None,
    }


async def _finalize_user_flow(
    prd_text: str,
    interview_history: list,
    final_answer: str,
) -> dict:
    """인터뷰 결과를 반영하여 최종 유저 플로우 DAG를 생성합니다."""
    llm = _get_llm("gpt-4o")

    # 대화 이력 직렬화
    history_text = ""
    for msg in interview_history:
        role = "AI" if msg.get("role") == "ai" else "기획자"
        history_text += f"[{role}] {msg.get('content', '')}\n\n"

    system_prompt = (
        "당신은 UX 설계 전문가이자 서비스 아키텍트입니다.\n"
        "기획자와의 인터뷰를 통해 확정된 기능 범위를 기반으로\n"
        "이 서비스의 **최종 유저 플로우(DAG)**를 생성하세요.\n\n"

        "## ⚠️ 핵심 규칙\n"
        "1. **인터뷰에서 확정된 기능만** 포함하세요.\n"
        "2. 기획자가 '불필요'라고 한 기능은 **절대 포함하지 마세요.**\n"
        "3. 기획자가 범위를 한정한 기능은 **해당 범위 내에서만** 설계하세요.\n"
        "4. DAG(방향 비순환 그래프) 구조로, 노드 간 공유가 가능합니다.\n"
        "5. node_type: screen(화면) | process(처리) | decision(분기)\n\n"

        "## 💡 출력 형식 (Strict JSON)\n"
        "{\n"
        '  "title": "서비스 유저 플로우 제목",\n'
        '  "nodes": [\n'
        '    {"name": "기능명", "description": "설명", "node_type": "screen|process|decision"}\n'
        "  ],\n"
        '  "edges": [\n'
        '    {"from": "노드명", "to": "노드명", "label": "조건"}\n'
        "  ]\n"
        "}\n"
    )

    user_message = (
        f"## PRD 원문\n{prd_text[:3000]}\n\n"
        f"## 인터뷰 전체 이력\n{history_text}\n\n"
        f"## 기획자의 최종 답변\n{final_answer}\n\n"
        "위 인터뷰 결과를 반영하여 유저 플로우 DAG를 생성하세요."
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    response = await llm.ainvoke(messages)

    try:
        result = _extract_json(response.content)
        print(f"[DEBUG _finalize_user_flow] LLM Raw Response:\n{response.content}\n")
        logger.info(
            f"[_finalize_user_flow] 최종 생성: 노드 {len(result.get('nodes', []))}개, "
            f"엣지 {len(result.get('edges', []))}개"
        )
        return {
            "action": "finalize",
            "message": "유저 플로우가 생성되었습니다.",
            "user_flow": result,
        }
    except Exception as e:
        logger.error(f"[_finalize_user_flow] JSON 파싱 에러: {e}")
        print(f"[DEBUG _finalize_user_flow ERROR] LLM Raw Response:\n{response.content}\n")
        raise ValueError(f"유저 플로우 최종 생성 실패: {e}")


async def generate_user_flow(
    prd_text: str,
    pdf_content: str = "",
) -> dict:
    """
    레거시 원샷 모드: PRD를 분석하여 서비스의 유저 플로우(DAG)를 바로 생성합니다.
    (인터뷰 없이 즉시 생성이 필요한 경우 사용)
    """
    ai_analysis = await analyze_prd_for_interview(prd_text, pdf_content)
    result = await _finalize_user_flow(
        prd_text=prd_text,
        interview_history=[{"role": "ai", "content": ai_analysis, "turn": 1}],
        final_answer="위 분석 결과 그대로 유저 플로우를 생성해주세요.",
    )
    return result["user_flow"]


# ──────────────────────────────────────────────
# Stage 2: 유저 플로우 노드 → ASCII 와이어프레임
# ──────────────────────────────────────────────

async def generate_wireframes(
    nodes: List[dict],
    edges: List[dict],
) -> List[dict]:
    """
    유저 플로우의 각 screen 노드에 대해 ASCII 와이어프레임을 생성합니다.

    Args:
        nodes: [{"name": "...", "description": "...", "node_type": "screen|process|decision"}]
        edges: [{"from_node": "...", "to_node": "...", "label": "..."}]

    Returns:
        [{"node_name": "로그인", "ascii": "┌───────┐\n│ ...   │\n└───────┘"}]
    """
    llm = _get_llm("gpt-4o")

    # screen 타입 노드만 필터링
    screen_nodes = [n for n in nodes if n.get("node_type", "screen") == "screen"]
    if not screen_nodes:
        screen_nodes = nodes  # 모두 screen이 아니면 전부 대상

    # 연결 관계 요약 생성
    edge_summary = ""
    for edge in edges:
        from_name = edge.get("from_node") or edge.get("from", "")
        to_name = edge.get("to_node") or edge.get("to", "")
        label = edge.get("label", "")
        edge_summary += f"  {from_name} → {to_name} ({label})\n"

    node_list = "\n".join([
        f"  - {n['name']}: {n.get('description', '')} (타입: {n.get('node_type', 'screen')})"
        for n in screen_nodes
    ])

    system_prompt = (
        "당신은 UI/UX 와이어프레임 전문 설계사입니다.\n"
        "제공된 유저 플로우 노드(화면)들에 대해 **ASCII 형태의 lo-fi 와이어프레임**을 생성하세요.\n\n"

        "## 📋 설계 원칙\n"
        "1. 모바일 앱 기준으로 설계 (세로형 레이아웃)\n"
        "2. 주요 UI 요소 배치: 헤더, 입력 필드, 버튼, 네비게이션 바, 카드, 리스트 등\n"
        "3. ASCII 박스 문자(┌─┐│└─┘) 사용\n"
        "4. 각 화면의 **핵심 기능과 이동 경로**를 반영\n"
        "5. 화면 간 연결 관계를 고려하여 일관된 네비게이션 구조 유지\n\n"

        "## 💡 ASCII 와이어프레임 예시\n"
        "```\n"
        "┌─────────────────────────────┐\n"
        "│  [← 뒤로]    로그인         │\n"
        "│                             │\n"
        "│  ┌───────────────────────┐  │\n"
        "│  │ 이메일                │  │\n"
        "│  └───────────────────────┘  │\n"
        "│  ┌───────────────────────┐  │\n"
        "│  │ 비밀번호   [👁]       │  │\n"
        "│  └───────────────────────┘  │\n"
        "│                             │\n"
        "│  [━━━━━━━ 로그인 ━━━━━━━]  │\n"
        "│                             │\n"
        "│  ─── 또는 ───               │\n"
        "│  [Google]  [Kakao]          │\n"
        "│                             │\n"
        "│  회원가입 | 비밀번호 찾기    │\n"
        "└─────────────────────────────┘\n"
        "```\n\n"

        "## 💡 출력 형식 (Strict JSON 배열)\n"
        "[\n"
        '  {"node_name": "로그인", "ascii": "┌──────────┐\\n│ ... │\\n└──────────┘"},\n'
        '  {"node_name": "홈 화면", "ascii": "┌──────────┐\\n│ ... │\\n└──────────┘"}\n'
        "]\n"
    )

    user_message = (
        f"## 대상 화면 노드\n{node_list}\n\n"
        f"## 화면 간 연결 관계\n{edge_summary}\n\n"
        "위 화면들에 대해 각각 ASCII 와이어프레임을 생성하세요."
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    response = await llm.ainvoke(messages)

    try:
        result = _extract_json(response.content)
        logger.info(f"[generate_wireframes] {len(result)}개 와이어프레임 생성")
        return result
    except Exception as e:
        logger.error(f"[generate_wireframes] JSON 파싱 에러: {e}, content: {response.content[:500]}")
        raise ValueError(f"와이어프레임 생성 JSON 파싱 실패: {e}")


# ──────────────────────────────────────────────
# Stage 3: 유저 플로우 + 와이어프레임 → 개발 태스크
# ──────────────────────────────────────────────

async def generate_pipeline_from_flow(
    nodes: List[dict],
    edges: List[dict],
    category: str = "BE",
    tech_stack: str = "Spring Boot, JPA",
) -> List[dict]:
    """
    유저 플로우 DAG와 와이어프레임을 기반으로 개발 태스크를 분해합니다.

    Returns:
        [
            {
                "title": "[회원가입] 이메일 기반 회원가입 API 구현",
                "details": ["...", "..."],
                "tech_stack": ["Spring Boot", "JPA"],
                "source_node_name": "회원가입",
                "category": "BE",
                "priority": 1
            }
        ]
    """
    llm = _get_llm("gpt-4o")

    # 노드 + 와이어프레임 통합 요약
    node_summaries = []
    for node in nodes:
        summary = f"### {node['name']} ({node.get('node_type', 'screen')})\n"
        summary += f"설명: {node.get('description', 'N/A')}\n"
        wireframe = node.get("wireframe_ascii", "")
        if wireframe:
            summary += f"와이어프레임:\n```\n{wireframe}\n```\n"
        node_summaries.append(summary)

    # 엣지 요약
    edge_summary = ""
    for edge in edges:
        from_name = edge.get("from_node") or edge.get("from", "")
        to_name = edge.get("to_node") or edge.get("to", "")
        label = edge.get("label", "")
        edge_summary += f"  {from_name} → {to_name} ({label})\n"

    scope_constraint = ""
    if category == "BE":
        scope_constraint = (
            "당신은 오직 **백엔드 서버와 데이터베이스** 아키텍처만 설계해야 합니다.\n"
            "- DB 스키마 설계 및 API 로직 구현에 집중하십시오.\n"
            "- UI/UX 구현은 절대 포함하지 마십시오."
        )
    elif category == "FE":
        scope_constraint = (
            "당신은 오직 **프론트엔드 및 클라이언트 애플리케이션**만 설계해야 합니다.\n"
            "- UI 컴포넌트 개발 및 API 연동에 집중하십시오.\n"
            "- DB 설계나 서버 측 트랜잭션 구현은 절대 포함하지 마십시오."
        )

    system_prompt = (
        f"🚀 FitHub AI: {category} 전문 파이프라인 설계 엔진\n"
        f"## ⚠️ 직군 격리 지침\n{scope_constraint}\n\n"

        "## 📋 핵심 원칙: 유저 플로우 기반 버티컬 슬라이스\n"
        "1. 제공된 **유저 플로우 DAG**와 **ASCII 와이어프레임**을 분석하세요.\n"
        "2. 각 유저 플로우 노드(기능)를 기반으로 **버티컬 슬라이스(Vertical Slice)** 방식의 개발 태스크를 생성하세요.\n"
        "3. 하나의 태스크는 Entity → Service → Controller → 테스트까지 **완전한 흐름**을 포함합니다.\n"
        "4. 각 태스크의 `source_node_name`에 어떤 유저 플로우 노드에서 파생되었는지 반드시 명시하세요.\n"
        "5. 최소 7개 이상의 구체적인 스텝으로 분리하세요.\n"
        "6. 각 스텝의 `details` 항목은 GitHub Issue로 발행 가능한 수준의 태스크여야 합니다.\n\n"

        "## 💡 5-200-4 규칙\n"
        "- 파일 수: 최대 5개 이하\n"
        "- 코드 라인: 최대 200 LOC 이하\n"
        "- 예상 소요 시간: 최대 4시간 이내\n"
        "- 기능이 크면 레이어가 아닌 '하위 기능'으로 분해\n\n"

        "## 💡 출력 형식 (Strict JSON 배열)\n"
        "[\n"
        "  {\n"
        '    "title": "[기능명] 원자적 작업 설명",\n'
        '    "details": ["[API] 구체적 태스크 1", "[DB] 구체적 태스크 2", "[Test] 구체적 태스크 3"],\n'
        '    "tech_stack": ["사용 기술"],\n'
        '    "source_node_name": "연결된 유저 플로우 노드명",\n'
        '    "category": "' + category + '",\n'
        '    "priority": 1\n'
        "  }\n"
        "]\n"
    )

    user_message = (
        f"## 기술 스택\n{tech_stack}\n\n"
        f"## 유저 플로우 노드 (화면 + 와이어프레임)\n{''.join(node_summaries)}\n\n"
        f"## 노드 간 연결 관계\n{edge_summary}\n\n"
        "위 유저 플로우와 와이어프레임을 기반으로 개발 파이프라인 태스크를 생성하세요."
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
    response = await llm.ainvoke(messages)

    try:
        result = _extract_json(response.content)
        logger.info(f"[generate_pipeline_from_flow] {len(result)}개 태스크 생성")

        # 정규화
        normalized = []
        for step in result:
            raw_details = step.get("details") or step.get("description") or ["상세 내용 정의 필요"]
            if isinstance(raw_details, str):
                raw_details = [raw_details]

            raw_tech = step.get("tech_stack") or step.get("tech") or []
            if isinstance(raw_tech, str):
                raw_tech = [raw_tech]

            normalized.append({
                "title": step.get("title", "분석된 작업"),
                "details": raw_details,
                "tech_stack": raw_tech,
                "source_node_name": step.get("source_node_name", ""),
                "category": step.get("category", category),
                "priority": step.get("priority", 1),
                "depends_on": step.get("depends_on", []),
            })

        return normalized
    except Exception as e:
        logger.error(f"[generate_pipeline_from_flow] JSON 파싱 에러: {e}, content: {response.content[:500]}")
        raise ValueError(f"파이프라인 생성 JSON 파싱 실패: {e}")

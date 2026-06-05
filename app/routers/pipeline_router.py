"""
Pipeline Router — REST API

엔드포인트:
  POST   /pipelines/             → 파이프라인 생성
  GET    /pipelines/{id}         → 파이프라인 단건 조회
  GET    /pipelines/project/{id} → 프로젝트별 파이프라인 목록
  PATCH  /pipelines/{id}         → 파이프라인 수정
  DELETE /pipelines/{id}         → 파이프라인 삭제

  POST   /pipelines/{id}/steps          → 스텝 추가
  PATCH  /pipelines/steps/{step_id}     → 스텝 수정
  DELETE /pipelines/steps/{step_id}     → 스텝 삭제

  POST   /pipelines/generate-and-save   → AI 생성 + DB 저장 (기본)
  POST   /pipelines/generate-2pass      → 2-Pass AI 생성 + DB 저장
  POST   /pipelines/interview           → Ouroboros 사전 인터뷰
"""
import logging
import tempfile
import os
from typing import Optional, List, Any, Dict, Union
import json

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession
from docling.document_converter import DocumentConverter
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from app.database import get_db
from app.config import get_settings
from app.schemas.pipeline import (
    PipelineCreate,
    PipelineGithubRepositoryUpdate,
    PipelineUpdate,
    PipelineResponse,
    PipelineListResponse,
    PipelineStepCreate,
    PipelineStepUpdate,
    PipelineStepResponse,
    PipelineV3Response,
    PipelineV3ListResponse,
    MeetingStepConfirmation,
)
from app.services import pipeline_service
from app.services import two_pass_pipeline_service
from app.graph.pipeline_graph import pipeline_graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["Pipelines"])

ALL_V3_CATEGORIES = ["BE", "FE"]

class InterviewRequest(BaseModel):
    user_message: str
    chat_history: List[Dict[str, str]] = [] # [{"role": "user"|"ai", "content": "..."}]
    context: str = ""

@router.post("/interview", summary="Ouroboros 사전 인터뷰")
async def ouroboros_interview(request: InterviewRequest):
    settings = get_settings()
    llm = ChatOpenAI(model="gpt-4o", temperature=0.5, api_key=settings.openai_api_key)
    
    system_prompt = (
        "당신은 Ouroboros 인터뷰어이자 수석 소프트웨어 아키텍트입니다.\n"
        "당신의 목표는 사용자가 제공한 기획 내용(Context)을 바탕으로, 개발 파이프라인을 짤 때 필요한 핵심 디테일을 '역질문'하여 끌어내는 것입니다.\n\n"
        "## 💡 인터뷰 지침\n"
        "- 한 번에 하나의 날카로운 질문만 던지세요.\n"
        "- 사용자에게 정답을 주입하지 말고, 스스로 생각하게 유도하세요 (소크라테스식 문답).\n\n"
        "## 💡 모호성 측정 (Ambiguity Scoring)\n"
        "- 현재까지의 요구사항 및 대화 내역이 '정밀한 개발 파이프라인을 구축하기에 충분한가'를 0~100점 사이로 측정하세요.\n"
        "- 80점 이상이면 대화를 종료해도 좋은 수준으로 간주합니다.\n\n"
        "## 💡 출력 가이드 (Strict JSON)\n"
        "반드시 아래 JSON 형식으로만 응답하세요.\n"
        "{\n"
        "  \"ai_reply\": \"사용자에게 던질 질문\",\n"
        "  \"options\": [\"추천 답변 선지 1\", \"추천 답변 선지 2\", \"추천 답변 선지 3\"],\n"
        "  \"ambiguity_score\": 85,\n"
        "  \"is_ready\": true\n"
        "}"
    )
    
    messages = [SystemMessage(content=system_prompt)]
    if request.context:
        messages.append(SystemMessage(content=f"<PRD_CONTEXT>\n{request.context}\n</PRD_CONTEXT>"))
        
    for chat in request.chat_history:
        if chat["role"] == "user":
            messages.append(HumanMessage(content=chat["content"]))
        else:
            messages.append(AIMessage(content=chat["content"]))
            
    messages.append(HumanMessage(content=request.user_message))
    
    # 지침 재강조 (대화가 길어져도 JSON 형식을 유지하도록 유도)
    messages.append(SystemMessage(content="""
    [MANDATORY RULE]
    1. 반드시 아래 JSON 형식을 지키세요.
    2. 'options' 필드는 절대로 비워두지 마세요. 사용자가 답변으로 선택할 수 있는 구체적인 문장 3개를 직접 만드세요.
    3. JSON 외의 일반 텍스트는 응답에 포함하지 마세요.
    """))
    
    response = llm.invoke(messages)
    logger.info(f"[Interview Response Raw]: {response.content}")
    
    try:
        content = response.content.strip()
        # JSON 블록 추출 로직 강화
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group()
        
        parsed = json.loads(content)
        # options 필드가 비어있을 경우 강제 생성 유도 (혹은 기본값)
        if not parsed.get("options"):
            parsed["options"] = ["더 자세히 설명해주세요.", "다음 단계로 넘어갈까요?", "다른 관점의 질문을 해주세요."]
        return parsed
    except Exception as e:
        logger.error(f"Interview JSON parsing error: {e}, content: {response.content}")
        return {
            "ai_reply": response.content,
            "options": ["예, 계속 진행해주세요.", "이해가 잘 안 됩니다.", "다른 대안을 제안해주세요."],
            "ambiguity_score": 50,
            "is_ready": False
        }

# ──────────────────────────────────────────────
# Pipeline CRUD
# ──────────────────────────────────────────────

@router.post(
    "/",
    response_model=PipelineResponse,
    status_code=201,
    summary="파이프라인 생성",
)
async def create_pipeline(
    data: PipelineCreate,
    db: AsyncSession = Depends(get_db),
):
    pipeline = await pipeline_service.create_pipeline(db, data)
    return pipeline


@router.get(
    "/{pipeline_id}",
    response_model=PipelineResponse,
    summary="파이프라인 단건 조회",
)
async def get_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.get_pipeline(db, pipeline_id)


@router.get(
    "/project/{project_id}",
    response_model=PipelineListResponse,
    summary="프로젝트별 파이프라인 목록",
)
async def get_pipelines_by_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    pipelines = await pipeline_service.get_pipelines_by_project(db, project_id)
    return PipelineListResponse(pipelines=pipelines, total=len(pipelines))


@router.patch(
    "/{pipeline_id}",
    response_model=PipelineResponse,
    summary="파이프라인 수정",
)
async def update_pipeline(
    pipeline_id: int,
    data: PipelineUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.update_pipeline(db, pipeline_id, data)


@router.patch(
    "/{pipeline_id}/github-repository",
    response_model=PipelineResponse,
    summary="파이프라인 GitHub repository URL 연결",
    description=(
        "특정 파이프라인의 GitHub repository URL만 부분 수정합니다. "
        "하나의 GitHub repository URL은 하나의 파이프라인에만 연결됩니다."
    ),
    response_description="GitHub repository URL이 연결된 파이프라인",
    responses={
        404: {"description": "파이프라인을 찾을 수 없음"},
        409: {"description": "이미 다른 파이프라인에 연결된 GitHub repository URL"},
    },
)
async def update_pipeline_github_repository(
    data: PipelineGithubRepositoryUpdate,
    pipeline_id: int = Path(..., description="GitHub repository URL을 연결할 파이프라인 ID", examples=[33]),
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.update_pipeline_github_repository_url(
        db,
        pipeline_id,
        data.github_repo_url,
    )


@router.delete(
    "/{pipeline_id}",
    status_code=204,
    summary="파이프라인 삭제",
)
async def delete_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
):
    await pipeline_service.delete_pipeline(db, pipeline_id)


# ──────────────────────────────────────────────
# Pipeline Step CRUD
# ──────────────────────────────────────────────

@router.post(
    "/{pipeline_id}/steps",
    response_model=PipelineStepResponse,
    status_code=201,
    summary="파이프라인에 스텝 추가",
)
async def create_step(
    pipeline_id: int,
    data: PipelineStepCreate,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.create_pipeline_step(db, pipeline_id, data)


@router.patch(
    "/steps/{step_id}",
    response_model=PipelineStepResponse,
    summary="파이프라인 스텝 수정",
)
async def update_step(
    step_id: int,
    data: PipelineStepUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.update_pipeline_step(db, step_id, data)


@router.patch(
    "/steps/{step_id}/confirm",
    response_model=PipelineStepResponse,
    summary="회의 기반 파이프라인 스텝 최종 승인",
    description="회의록(meeting_id)의 승인 상태를 확인하여 파이프라인 스텝을 최종 승인(Approved) 처리합니다.",
)
async def confirm_step(
    step_id: int,
    data: MeetingStepConfirmation,
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_service.confirm_pipeline_step_via_meeting(
        db, step_id, data.meeting_id
    )


@router.delete(
    "/steps/{step_id}",
    status_code=204,
    summary="파이프라인 스텝 삭제",
)
async def delete_step(
    step_id: int,
    db: AsyncSession = Depends(get_db),
):
    await pipeline_service.delete_pipeline_step(db, step_id)


# ──────────────────────────────────────────────
# AI Generate + DB Save (기존 /pipeline/generate 확장)
# ──────────────────────────────────────────────

@router.post(
    "/generate-and-save",
    response_model=PipelineResponse,
    summary="AI 파이프라인 생성 → DB 저장",
    description=(
        "PRD PDF + 요구사항 텍스트로 LangGraph AI 파이프라인을 생성하고 "
        "결과를 DB에 저장합니다. 기존 활성 파이프라인은 비활성화됩니다."
    ),
)
async def generate_and_save_pipeline(
    project_id: int = Form(..., description="Spring DB의 project ID (Logical FK)"),
    requirements: str = Form(..., description="기획자 요구사항 텍스트"),
    category: Optional[str] = Form(None, description="파이프라인 카테고리"),
    prd_file: Optional[UploadFile] = File(None, description="PRD PDF 파일 (선택)"),
    db: AsyncSession = Depends(get_db),
):
    # PDF 바이트 읽기
    pdf_bytes: Optional[bytes] = None
    if prd_file is not None:
        if not prd_file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")
        pdf_bytes = await prd_file.read()

    # LangGraph 실행
    try:
        result = await pipeline_graph.ainvoke({
            "requirements": requirements,
            "pdf_bytes": pdf_bytes,
            "category": category or "BE",
            "parsed_text": "",
            "prd_summary": "",
            "domains": [],
            "framework": None,
            "template_stages": None,
            "raw_items": "",
            "pipeline": [],
        })
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI 파이프라인 생성 중 오류: {str(e)}",
        )

    pipeline_items = result.get("pipeline", [])
    if not pipeline_items:
        raise HTTPException(
            status_code=500,
            detail="AI가 파이프라인 아이템을 생성하지 못했습니다.",
        )

    # DB 저장
    pipeline = await pipeline_service.save_ai_pipeline_to_db(
        db, project_id, pipeline_items, category
    )
    return pipeline


# ──────────────────────────────────────────────
# 2-Pass AI Pipeline Generation
# ──────────────────────────────────────────────


@router.post(
    "/generate-2pass",
    response_model=PipelineListResponse,
    summary="2-Pass AI 파이프라인 생성 → DB 저장",
    description=(
        "2-Pass 시스템으로 AI 파이프라인을 생성하고 DB에 저장합니다.\n\n"
        "**Pass 1 (Planner)**: gpt-4o로 PDF 분석 → 파이프라인 방향성(Direction) 도출\n"
        "**Pass 2 (Builder)**: gpt-4o-mini로 각 Direction을 병렬 처리 → 구체적 스텝 생성\n\n"
        "결과: 프로젝트별로 여러 파이프라인 생성 (BE, FE, AI, DevOps 등)"
    ),
)
async def generate_2pass_pipeline(
    project_id: int = Form(..., description="Spring DB의 project ID (Logical FK)"),
    requirements: str = Form(..., description="기획자 요구사항 텍스트"),
    category: Optional[str] = Form(
        None, description="특정 카테고리만 생성 (예: 'BE'). None이면 모든 카테고리"
    ),
    prd_file: Optional[UploadFile] = File(None, description="PRD PDF 파일 (선택)"),
    db: AsyncSession = Depends(get_db),
):
    """
    2-Pass 파이프라인 생성 및 DB 저장

    1. PDF 파싱 (Docling)
    2. Pass 1 (Planner): PDF 분석 → Direction 도출
    3. Pass 2 (Builder): Direction 병렬 처리 → Step 생성
    4. PipelineCreate 조립 → DB 저장
    5. 결과 반환
    """
    # PDF 파싱
    pdf_text = ""
    if prd_file is not None:
        if not prd_file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")

        # PDF 바이트 읽기
        pdf_bytes = await prd_file.read()

        # 임시 파일로 저장하여 Docling 처리
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            pdf_text = result.document.export_to_markdown()
            logger.info(f"PDF 파싱 완료: {len(pdf_text)} 문자")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PDF 파싱 실패: {str(e)}")
        finally:
            os.unlink(tmp_path)

    # 2-Pass 파이프라인 생성
    try:
        pipelines_create = await two_pass_pipeline_service.generate_pipeline_from_pdf(
            project_id=project_id,
            pdf_text=pdf_text,
            category=category,
        )
        logger.info(f"2-Pass 파이프라인 생성 완료: {len(pipelines_create)}개 파이프라인")
    except Exception as e:
        logger.error(f"2-Pass 파이프라인 생성 실패: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"2-Pass 파이프라인 생성 중 오류: {str(e)}",
        )

    if not pipelines_create:
        raise HTTPException(
            status_code=500,
            detail="2-Pass AI가 파이프라인을 생성하지 못했습니다.",
        )

    # DB 저장
    saved_pipelines = []
    for pipeline_create in pipelines_create:
        try:
            pipeline = await pipeline_service.save_ai_pipeline_to_db(
                db=db,
                project_id=project_id,
                pipeline_items=[
                    {
                        "title": step.title,
                        "priority": idx + 1,
                        "details": step.description.split("\n")
                        if step.description
                        else [],
                        "duration": step.duration or "",
                        "tech_stack": step.tech_stack or "",
                    }
                    for idx, step in enumerate(pipeline_create.steps or [])
                ],
                category=pipeline_create.category,
            )
            saved_pipelines.append(pipeline)
            logger.info(
                f"파이프라인 DB 저장: {pipeline_create.category} (v{pipeline.version})"
            )
        except Exception as e:
            logger.error(
                f"파이프라인 DB 저장 실패 ({pipeline_create.category}): {e}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"파이프라인 DB 저장 실패: {str(e)}",
            )

    return PipelineListResponse(
        pipelines=saved_pipelines,
        total=len(saved_pipelines),
    )


# ──────────────────────────────────────────────
# V3 AI Pipeline Generation (Orchestrator-Worker)
# ──────────────────────────────────────────────

async def _generate_and_save_v3_pipeline_for_category(
    db: AsyncSession,
    graph,
    project_id: int,
    requirements: str,
    category: str,
    tech_stack: Optional[str],
    pdf_bytes: Optional[bytes],
) -> PipelineV3Response:
    """V3 그래프를 단일 카테고리로 실행하고 DB 저장 후 V3 응답으로 변환합니다."""
    normalized_category = category.strip().upper()

    try:
        result = await graph.ainvoke({
            "prd_context": requirements,
            "technical_stack": tech_stack or "최적 스택",
            "todos": [],
            "completed_steps": [],
            "feedback": "",
            "iteration_count": 0,
            "pdf_bytes": pdf_bytes,
            "interview_summary": "",
            "pdf_content": "",
            "refined_requirements": "",
            "category": normalized_category,
            "final_pipeline": [],
        }, config={"recursion_limit": 1000})
    except Exception as e:
        logger.error(f"V3 파이프라인 생성 실패 ({normalized_category}): {e}")
        raise HTTPException(
            status_code=500,
            detail=f"V3 파이프라인 생성 중 오류: {str(e)}",
        )

    pipeline_items = result.get("final_pipeline", [])
    if not pipeline_items:
        raise HTTPException(
            status_code=500,
            detail=f"{normalized_category} 카테고리 파이프라인 아이템을 생성하지 못했습니다.",
        )

    pipeline = await pipeline_service.save_ai_pipeline_to_db(
        db, project_id, pipeline_items, normalized_category, tech_stack
    )
    return PipelineV3Response.model_validate(pipeline)

@router.post(
    "/generate-v3",
    response_model=Union[PipelineV3Response, PipelineV3ListResponse],
    summary="V3 AI 파이프라인 생성 (Orchestrator-Worker) → DB 저장",
    description=(
        "Pipe.md 기반 원자적 작업(Atomic Task) 분해 로직을 적용한 파이프라인 생성입니다.\n"
        "Orchestrator(도메인 분해) → Worker(5-200-4 규칙 기반 태스크 생성) → Critic(품질 검증) "
        "순환 루프를 통해 가장 정밀한 파이프라인을 구축합니다."
    ),
)
async def generate_v3_pipeline(
    project_id: int = Form(..., description="Spring DB의 project ID (Logical FK)"),
    requirements: str = Form(..., description="기획자 요구사항 텍스트"),
    category: Optional[str] = Form(None, alias="category", description="파이프라인 카테고리 (예: 'BE')"),
    tech_stack: Optional[str] = Form(None, description="사용할 기술 스택 (예: 'Spring Boot, JPA')"),
    file: Optional[UploadFile] = File(None, description="PRD PDF 파일 (선택)"),
    db: AsyncSession = Depends(get_db),
):
    from app.graph.pipeline_graph_v3 import pipeline_graph_v3
    
    # PDF 바이트 읽기
    pdf_bytes: Optional[bytes] = None
    if file is not None:
        logger.info(f"[generate_v3_pipeline] 파일 수신됨: {file.filename}, 컨텐츠 타입: {file.content_type}")
        if not file.filename.endswith(".pdf"):
            raise HTTPException(status_code=400, detail="PDF 파일만 업로드 가능합니다.")
        pdf_bytes = await file.read()
        logger.info(f"[generate_v3_pipeline] PDF 데이터 읽기 완료: {len(pdf_bytes)} bytes")
    else:
        logger.warning("[generate_v3_pipeline] 수신된 파일이 없습니다.")

    normalized_category = (category or "BE").strip().upper()
    categories = ALL_V3_CATEGORIES if normalized_category == "ALL" else [normalized_category]

    pipelines = []
    for category_name in categories:
        pipelines.append(await _generate_and_save_v3_pipeline_for_category(
            db=db,
            graph=pipeline_graph_v3,
            project_id=project_id,
            requirements=requirements,
            category=category_name,
            tech_stack=tech_stack,
            pdf_bytes=pdf_bytes,
        ))

    if normalized_category == "ALL":
        return PipelineV3ListResponse(pipelines=pipelines, total=len(pipelines))

    return pipelines[0]

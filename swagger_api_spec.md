# 🚀 fitai — AI Pipeline & Meeting Intelligence API 명세

본 문서는 FastAPI의 Swagger UI(`http://localhost:8000/docs`)에서 노출되는 공식 OpenAPI 명세를 마크다운 형태로 정확하게 옮긴 것입니다. Spring 서버나 프론트엔드 연동 시 구조체 스키마로 활용해 주세요.

---

## 🏗️ 1. Pipelines Domain (`/pipelines`)
*파이프라인 및 LangGraph AI 스텝 관리*

### `POST` `/pipelines/generate-and-save`
> **AI 파이프라인 생성 및 DB 저장 (메인)**
> PRD PDF + 요구사항 텍스트로 LangGraph AI 파이프라인을 생성하고 결과를 DB에 저장합니다. 기존 활성 파이프라인은 비활성화됩니다.

**Request (FormData)**
```json
{
  "project_id": "integer (필수, Spring 프로젝트 ID)",
  "requirements": "string (필수, 기획 요구사항 텍스트)",
  "category": "string (선택)",
  "prd_file": "file (선택, PDF)"
}
```

**Response (200 OK: PipelineResponse)**
```json
{
  "id": 1,
  "project_id": 1,
  "category": "string",
  "version": 1,
  "is_active": true,
  "steps": [
    {
      "id": 1,
      "pipeline_id": 1,
      "title": "명확한 스텝 제목",
      "description": "세부 구현 내용",
      "is_completed": false,
      "origin": "ai_generated"
    }
  ]
}
```

---

### `GET` `/pipelines/project/{project_id}`
> **프로젝트별 파이프라인 목록 가져오기**

**Request (Path Parameter)**
- `project_id` (integer)

**Response (200 OK: PipelineListResponse)**
```json
{
  "pipelines": [
    {
      "id": 1,
      "project_id": 1,
      "category": "기능 개발",
      "version": 2,
      "is_active": true,
      "steps": [...]
    }
  ],
  "total": 1
}
```

---

### `POST` `/pipelines/{pipeline_id}/steps`
> **파이프라인 스텝 단일 추가 (수동)**

**Request (JSON Body: PipelineStepCreate)**
```json
{
  "title": "회원가입 기능 개발",
  "description": "소셜 로그인 연동 작업",
  "is_completed": false,
  "origin": "user_created"
}
```

**Response (201 Created)**
*생성된 Step 객체 반환 (`PipelineStepResponse`)*

---

### `PATCH` `/pipelines/steps/{step_id}`
> **파이프라인 스텝 수정 (완료 처리 등)**

**Request (JSON Body: PipelineStepUpdate)**
```json
{
  "is_completed": true
}
```

---

## 🗣️ 2. Meetings Domain (`/meetings`)
*회의록 및 AI 요약 통찰 도메인*

### `POST` `/meetings/`
> **회의록 원본 생성 및 참석자 매핑**

**Request (JSON Body: MeetingLogCreate)**
```json
{
  "project_id": 1,
  "content": "오늘 회의 내용 원본 스크립트...",
  "attendee_user_ids": [12, 13, 14] 
}
```
*(※ `attendee_user_ids`: Spring User DB 로지컬 FK 배열)*

**Response (201 Created: MeetingLogResponse)**
```json
{
  "id": 1,
  "project_id": 1,
  "content": "오늘 회의 내용 원본 스크립트...",
  "summary": null,
  "vector_id": null,
  "created_at": "2026-04-09T14:30:00Z",
  "attendees": [
    { "id": 1, "meeting_log_id": 1, "user_id": 12 },
    { "id": 2, "meeting_log_id": 1, "user_id": 13 }
  ],
  "step_relations": []
}
```

---

### `POST` `/meetings/{meeting_id}/summarize`
> **AI 회의록 요약 (메인)**
> GPT-4o로 회의록을 요약하고, 개발 파이프라인에 반영할 액션 아이템(가상 스텝)을 도출하여 DB에 업데이트합니다.

**Request (Path Parameter)**
- `meeting_id` (integer)

**Response (200 OK: MeetingSummarizeResponse)**
```json
{
  "meeting_log_id": 1,
  "summary": "핵심: ~~~ 결정사항: ~~~",
  "derived_steps": [
    "로그인 보안 검수 항목 추가",
    "이메일 인증 모듈 결합"
  ]
}
```

---

### `POST` `/meetings/{meeting_id}/attendees`
> **특정 회의록에 유저(참석자) 추가**

**Request (JSON Body: MeetingAttendeeCreate)**
```json
{
  "user_id": 15
}
```

---

### `POST` `/meetings/{meeting_id}/steps/{step_id}`
> **회의록과 생성된 파이프라인 스텝의 상관 관계 연결**
> (Spring 쪽 상관관계 추적용도로 활용)

**Request (Path Parameters)**
- `meeting_id` (integer)
- `step_id` (integer)

**Response (201 Created)**
```json
{
  "id": 1,
  "meeting_log_id": 1,
  "pipeline_step_id": 4
}
```

---

### 🚨 Common Errors (공통 에러 반환 스키마)
```json
// 422 Validation Error
{
  "detail": [
    {
      "loc": ["body", "project_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}

// 404 Not Found
{
  "detail": "회의록을 찾을 수 없습니다."
}
```

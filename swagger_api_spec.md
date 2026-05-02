# 🚀 fitai — AI Pipeline & Meeting Intelligence API 명세

본 문서는 FastAPI 서버(`http://localhost:8000/docs`)의 실제 OpenAPI 스펙을 기반으로 작성되었습니다.

---

## 🏗️ 1. Pipelines Domain (`/pipelines`)

---

### `POST` `/pipelines/generate-v3` ⭐ (추천)
> **V3 AI 파이프라인 생성 (Orchestrator-Worker) → DB 저장**
> Pipe.md 기반 원자적 작업(Atomic Task) 분해 로직을 적용한 파이프라인 생성입니다.
> Orchestrator(도메인 분해) → Worker(5-200-4 규칙 기반 태스크 생성) → Critic(품질 검증) 순환 루프를 통해 가장 정밀한 파이프라인을 구축합니다.

**Request (multipart/form-data)**

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `project_id` | integer | ✅ | Spring DB의 project ID (Logical FK) |
| `requirements` | string | ✅ | 기획자 요구사항 텍스트 |
| `category` | string \| null | ❌ | 파이프라인 카테고리 (예: 'BE') |
| `prd_file` | binary (file) \| null | ❌ | PRD PDF 파일 |

**Response (200 OK: `PipelineResponse`)**
```json
{
  "id": 12,
  "project_id": 1,
  "category": "BE",
  "version": 4,
  "is_active": "Active",
  "steps": [
    {
      "id": 101,
      "pipeline_id": 12,
      "step_task_description": "[회원가입] - OAuth2.0 연동 및 유저 저장\n1. User Entity 생성...\n2. OAuth Service 구현...",
      "step_sequence_number": 1,
      "step_github_status": "Open",
      "step_planner_confirm_yn": "Pending",
      "step_developer_confirm_yn": "Pending",
      "step_confirmation_date": null,
      "step_final_confirmed_status": "Pending",
      "duration": "4 hours",
      "tech_stack": "FastAPI, SQLAlchemy",
      "origin": "ai_generated",
      "created_at": "2026-05-02T14:00:00",
      "updated_at": null
    }
  ]
}
```

---

### `POST` `/pipelines/generate-and-save`
> **AI 파이프라인 생성 → DB 저장 (기본)**

**Request (multipart/form-data)**: `generate-v3`와 동일

**Response (200 OK: `PipelineResponse`)**: `generate-v3`와 동일

---

### `POST` `/pipelines/generate-2pass`
> **2-Pass AI 파이프라인 생성 → DB 저장**
> Pass 1 (Planner): gpt-4o → Direction 도출
> Pass 2 (Builder): gpt-4o-mini → 구체적 스텝 생성

**Request (multipart/form-data)**: `generate-v3`와 동일 (단, `category`가 null이면 모든 카테고리 생성)

**Response (200 OK: `PipelineListResponse`)**
```json
{
  "pipelines": [
    { "id": 1, "project_id": 1, "category": "BE", "version": 1, "is_active": "Active", "steps": [...] },
    { "id": 2, "project_id": 1, "category": "FE", "version": 1, "is_active": "Active", "steps": [...] }
  ],
  "total": 2
}
```

---

### `POST` `/pipelines/`
> **파이프라인 수동 생성**

**Request (JSON Body: `PipelineCreate`)**
```json
{
  "project_id": 1,
  "category": "BE",
  "version": 1,
  "is_active": "Active",
  "steps": [
    {
      "step_task_description": "작업 내용",
      "step_sequence_number": 1,
      "duration": "2일",
      "tech_stack": "Spring Boot",
      "origin": "user_created"
    }
  ]
}
```

**Response (201 Created: `PipelineResponse`)**

---

### `GET` `/pipelines/{pipeline_id}`
> **파이프라인 단건 조회**

**Response (200 OK: `PipelineResponse`)**

---

### `GET` `/pipelines/project/{project_id}`
> **프로젝트별 파이프라인 목록**

**Response (200 OK: `PipelineListResponse`)**

---

### `PATCH` `/pipelines/{pipeline_id}`
> **파이프라인 수정**

**Request (JSON Body: `PipelineUpdate`)**
```json
{
  "category": "FE",
  "version": 2,
  "is_active": "Inactive"
}
```

---

### `DELETE` `/pipelines/{pipeline_id}`
> **파이프라인 삭제** (204 No Content)

---

### `POST` `/pipelines/{pipeline_id}/steps`
> **파이프라인에 스텝 추가**

**Request (JSON Body: `PipelineStepCreate`)**
```json
{
  "step_task_description": "작업 내용",
  "step_sequence_number": 1,
  "duration": "3일",
  "tech_stack": "React 18",
  "origin": "user_created"
}
```

**Response (201 Created: `PipelineStepResponse`)**

---

### `PATCH` `/pipelines/steps/{step_id}`
> **파이프라인 스텝 수정 (승인/완료 처리 등)**

**Request (JSON Body: `PipelineStepUpdate`)**
```json
{
  "step_task_description": "수정된 내용",
  "step_sequence_number": 2,
  "step_github_status": "Closed",
  "step_planner_confirm_yn": "Approved",
  "step_developer_confirm_yn": "Approved",
  "duration": "2일",
  "tech_stack": "Spring Boot 3.x",
  "origin": "user_created"
}
```

**Response (200 OK: `PipelineStepResponse`)**

---

### `DELETE` `/pipelines/steps/{step_id}`
> **파이프라인 스텝 삭제** (204 No Content)

---

## 📊 스키마 상세 (Pipelines)

### `PipelineResponse`
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `id` | integer | ✅ | 파이프라인 ID |
| `project_id` | integer | ✅ | 프로젝트 ID |
| `category` | string \| null | ❌ | 카테고리 |
| `version` | integer | ✅ | 버전 |
| `is_active` | string | ✅ | "Active" \| "Inactive" |
| `steps` | PipelineStepResponse[] | ❌ | 스텝 목록 (기본값 []) |

### `PipelineStepResponse`
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `id` | integer | ✅ | 스텝 ID |
| `pipeline_id` | integer | ✅ | 소속 파이프라인 ID |
| `step_task_description` | string | ✅ | 작업 상세 내용 |
| `step_sequence_number` | integer | ✅ | 작업 배치 순서 |
| `step_github_status` | string | ✅ | "Open" \| "Closed" |
| `step_planner_confirm_yn` | string | ✅ | "Pending" \| "Approved" |
| `step_developer_confirm_yn` | string | ✅ | "Pending" \| "Approved" |
| `step_confirmation_date` | datetime \| null | ❌ | 양측 승인 완료 날짜 |
| `step_final_confirmed_status` | string | ✅ | "Pending" \| "Confirmed" (계산 필드) |
| `duration` | string \| null | ❌ | 예상 소요 시간 |
| `tech_stack` | string \| null | ❌ | 기술 스택 |
| `origin` | string \| null | ❌ | "ai_generated" \| "user_created" \| "meeting_derived" |
| `created_at` | datetime \| null | ❌ | 생성 시각 |
| `updated_at` | datetime \| null | ❌ | 수정 시각 |

---

## 🗣️ 2. Meetings Domain (`/meetings`)

### `POST` `/meetings/`
> **회의록 생성**

**Request (JSON Body: `MeetingLogCreate`)**
```json
{
  "project_id": 1,
  "content": "회의 원본 내용",
  "meeting_log_content": null,
  "ai_translated_explanation": null,
  "attendee_user_ids": [1, 2, 3]
}
```

### `GET` `/meetings/{meeting_id}`
> **회의록 단건 조회** → `MeetingLogResponse`

### `PATCH` `/meetings/{meeting_id}`
> **회의록 수정** → `MeetingLogUpdate`

### `DELETE` `/meetings/{meeting_id}`
> **회의록 삭제** (204)

### `GET` `/meetings/project/{project_id}`
> **프로젝트별 회의록 목록** → `MeetingLogListResponse`

### `POST` `/meetings/{meeting_id}/attendees`
> **회의 참석자 추가**

### `DELETE` `/meetings/attendees/{attendee_id}`
> **회의 참석자 제거** (204)

### `POST` `/meetings/{meeting_id}/steps/{step_id}`
> **회의록 ↔ 파이프라인 스텝 연결**

### `DELETE` `/meetings/step-relations/{relation_id}`
> **회의록 ↔ 스텝 연결 해제** (204)

### `POST` `/meetings/{meeting_id}/summarize`
> **AI 회의록 요약**

**Response (200 OK: `MeetingSummarizeResponse`)**
```json
{
  "meeting_log_id": 1,
  "summary": "핵심 내용 요약...",
  "derived_steps": ["로그인 보안 검수 추가", "이메일 인증 모듈 결합"]
}
```
---

## 🔍 3. Translation Domain (`/meetings/...`)

### `GET` `/meetings/search`
> **번역 세션 검색 (임베딩 기반)**

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `query` | string (min 2) | ✅ | 검색 쿼리 |
| `limit` | integer (1~100) | ❌ | 최대 결과 수 (기본 10) |

### `POST` `/meetings/{meeting_id}/translate-to-technical`
> **기획자 → 개발자 번역**

**Request**
```json
{
  "original_statement": "사용자 추천 기능 만들어줘",
  "context": "이커머스 서비스"
}
```

**Response**
```json
{
  "meeting_id": 1,
  "original_statement": "사용자 추천 기능 만들어줘",
  "ai_translation": {
    "problem_statement": "유저 행동 기반 추천 시스템 구현",
    "technical_approach": ["협업 필터링 적용", "사용자 행동 로그 수집"],
    "tech_stack": ["Python", "scikit-learn"],
    "effort_estimate": "5-7일",
    "dependencies": ["사용자 행동 로그 테이블 필요"]
  },
  "saved_at": "2026-05-02T14:00:00"
}
```

### `POST` `/meetings/{meeting_id}/translate-to-planning`
> **개발자 → 기획자 번역**

### `POST` `/meetings/{meeting_id}/finalize-translation-session`
> **번역 세션 종료 및 지식화**

### `GET` `/meetings/{meeting_id}/translation-history`
> **번역 이력 조회**

---

## 🚨 Common Errors

| 상태 코드 | 설명 |
|-----------|------|
| `400` | PDF 파일만 업로드 가능합니다 |
| `404` | 리소스를 찾을 수 없습니다 |
| `422` | 요청 데이터 형식 오류 (Validation Error) |
| `500` | AI 모델 호출 실패 또는 서버 내부 오류 |

```json
// 422 Validation Error
{
  "detail": [
    {
      "loc": ["body", "project_id"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

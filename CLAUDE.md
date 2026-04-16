# 🎯 FitHub - AI 기반 프로젝트 협업 허브

## 📋 Project Overview

**FitHub**는 기획자와 개발자 간의 협업 문제를 AI 기술로 해결하는 프로젝트 관리 시스템입니다.

### 핵심 문제
- 기획자와 개발자의 언어/관점 차이로 인한 의사소통 문제
- 기획자가 GitHub 이슈/PR을 이해하기 어려움
- 개발 상황 공유의 비효율성
- 새로운 기능의 기술적 가능성 검증 프로세스 부족

### 핵심 솔루션
✅ **AI 기반 자동 언어 변환**: 기획자 ↔ 개발자 언어 상호 변환
✅ **GitHub 연동**: 커밋, 이슈, PR 실시간 수집 및 시각화
✅ **프로젝트 지식 축적**: 회의록, 기획서, 코드 등을 통합 관리
✅ **협업 허브**: 기획자용 직관적 UI로 진행 상황 모니터링

---

## 🏗️ Architecture

### MSA (Microservices Architecture) - 독립적 DB

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend Layer                               │
│                 (React Native / Web Browser)                         │
└────────────────┬──────────────────────────────────┬──────────────────┘
                 │ REST API                         │ REST API
                 ▼                                   ▼
    ┌────────────────────────┐         ┌────────────────────────┐
    │   Spring Server        │         │  FastAPI Server        │
    │   (비즈니스 로직)        │         │  (AI Pipeline 로직)     │
    │                        │         │                        │
    │ - 사용자 관리          │         │ - LLM 처리             │
    │ - 프로젝트 관리        │         │ - PDF 분석             │
    │ - 이슈 추적            │         │ - 파이프라인 생성      │
    │ - GitHub 연동          │         │ - 회의 기록 관리       │
    │                        │         │                        │
    └────────────┬───────────┘         └──────────┬─────────────┘
                 │                                  │
                 ▼ RestClient                       ▼ RestClient
    ┌────────────────────────┐         ┌────────────────────────┐
    │   Spring DB            │         │  FastAPI DB            │
    │  (H2 / PostgreSQL)     │         │ (SQLite / PostgreSQL)  │
    │                        │         │                        │
    │ - users                │         │ - pipelines            │
    │ - projects             │         │ - pipeline_steps       │
    │ - project_members      │         │ - meeting_logs         │
    │ - repositories         │         │ - meeting_attendees    │
    │ - issues               │         │ - meeting_step_relations
    │ - issue_syncs          │         │                        │
    └────────────────────────┘         └────────────────────────┘
                 ▲                                  ▲
                 │                                  │
                 └──────── Logical FK 참조 ────────┘
                 (물리적 외래키 없음 / API로 동기화)
```

### 데이터 흐름

**Logical FK 관계:**
- `issues.pipeline_step_id` → `fastapi.pipeline_steps.id`
- `pipelines.project_id` → `spring.projects.id`
- `meeting_logs.project_id` → `spring.projects.id`
- `meeting_attendees.user_id` → `spring.users.id`

**통신 방식:**
- Spring Server ⇄ FastAPI Server: **REST API** (RestClient)
- 동기화: **Webhook** 또는 **폴링** (API 호출)
- 트랜잭션: 각 서버에서 독립적으로 관리

### 현재 개발 범위 (FastAPI Server)
- **FastAPI** 기반 RESTful API
- **LangGraph** 기반 AI 파이프라인 워크플로우 (5-Node)
- **SQLAlchemy** ORM으로 독립 DB 관리
- **OpenAI GPT-4o** 활용한 자연어 처리
- **Docling** PDF 파싱
- **비동기 처리**: asyncio, async/await

---

## 📁 Project Structure

```
fitai/
├── app/
│   ├── main.py                    # FastAPI 앱 엔트리포인트
│   ├── config.py                  # 환경 설정
│   ├── database.py                # SQLAlchemy 설정
│   ├── models/
│   │   ├── pipeline.py            # PipelineItem (LLM 출력)
│   │   └── db/
│   │       └── pipeline.py        # PipelineStep (DB ORM)
│   ├── schemas/
│   │   └── pipeline.py            # Request/Response DTO
│   ├── services/
│   │   └── pipeline_service.py    # 비즈니스 로직
│   ├── routers/
│   │   └── pipeline_router.py     # API 엔드포인트
│   └── graph/
│       └── pipeline_graph.py      # LangGraph 워크플로우
├── requirements.txt               # Python 의존성
├── .env                           # 환경변수 (OPENAI_API_KEY, etc)
└── CLAUDE.md                      # 이 파일
```

---

## 🔄 Pipeline Generation Workflow

### LangGraph 5-Node Workflow

```
1. parse_pdf        → PDF 파싱 (Docling)
2. understand_prd   → PRD 요약 분석 (GPT-4o)
3. identify_domains → 도메인 영역 식별
4. generate_items   → 파이프라인 아이템 생성
5. prioritize       → 검증 및 우선순위 정렬
```

### 데이터 흐름

**Input**: PDF + 요구사항 텍스트 + 카테고리 (FE/BE/AI)

**Process**:
- LLM이 5개 노드를 순차 실행
- 각 단계에서 상세한 분석 및 생성
- 최종적으로 구체적인 파이프라인 아이템 생성

**Output**:
```json
{
  "pipeline": [
    {
      "title": "JWT 토큰 발급 및 검증",
      "priority": 1,
      "duration": "2일",
      "details": [
        "JWT 생성 로직 구현...",
        "토큰 검증 미들웨어...",
        "RefreshToken 관리..."
      ]
    }
  ]
}
```

---

## 📊 Data Models

### PipelineItem (메모리 / API 응답)
```python
class PipelineItem(BaseModel):
    title: str              # "JWT 토큰 발급 및 검증"
    priority: int           # 1 (낮을수록 먼저 수행)
    duration: str           # "2일", "1주"
    details: List[str]      # ["JWT 생성...", "토큰 검증...", ...]
```

**역할**: LangGraph가 생성하는 중간 결과물
- **위치**: 메모리/API 응답
- **생성 단계**: `generate_items` 노드
- **사용처**: DB 저장 전 검증, API 응답

---

### PipelineStep (DB ORM)
```python
class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id: int                 # PK (자동 생성)
    pipeline_id: int        # FK → pipelines.id
    title: str              # "JWT 토큰 발급 및 검증"
    description: str        # "JWT 생성...\n토큰 검증..."  (details 병합)
    duration: str           # "2일"
    is_completed: bool      # False
    origin: str             # "ai_generated"
    created_at: datetime    # 자동 생성
```

**역할**: 데이터베이스에 영속화된 최종 데이터
- **위치**: SQLite / PostgreSQL
- **저장 단계**: `save_ai_pipeline_to_db` 함수
- **사용처**: 프론트엔드 조회, 완료 상태 관리

---

### 데이터 흐름: PipelineItem → PipelineStep

```
┌─────────────────────────────────────────┐
│  LangGraph generate_items 노드           │
│  (GPT-4o 기반 생성)                      │
└────────────┬────────────────────────────┘
             │
             ▼
    PipelineItem (메모리)
    {
      "title": "JWT 토큰 발급...",
      "priority": 1,
      "duration": "2일",
      "details": [...]
    }
             │
             ▼
  ┌──────────────────────────┐
  │ prioritize 노드          │
  │ (우선순위 정렬)           │
  └──────────┬───────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│  save_ai_pipeline_to_db                 │
│  (PipelineItem → PipelineStepCreate)    │
└────────────┬────────────────────────────┘
             │
             ▼
    PipelineStep (DB)
    {
      "id": 45,
      "pipeline_id": 5,
      "title": "JWT 토큰 발급...",
      "description": "JWT 생성...\n토큰 검증...",
      "duration": "2일",
      "is_completed": false,
      "origin": "ai_generated"
    }
             │
             ▼
  ┌──────────────────────────┐
  │ API 응답 (프론트 반환)    │
  │ PipelineStepResponse     │
  └──────────────────────────┘
```

---

### Logical FK 참조 (Spring ↔ FastAPI)

| 필드 | FastAPI DB | → | Spring DB |
|------|-----------|---|----------|
| `pipelines.project_id` | (Logical FK) | → | `projects.id` |
| `pipeline_steps.id` | (참조 가능) | ← | `issues.pipeline_step_id` |
| `meeting_logs.project_id` | (Logical FK) | → | `projects.id` |
| `meeting_attendees.user_id` | (Logical FK) | → | `users.id` |

**⚠️ 주의:** 물리적 외래키 없음 → API 호출로 데이터 검증

---

## 🎯 Development Conventions

### API 엔드포인트 (현재)
- `POST /api/pipelines/generate-and-save` - 파이프라인 생성 및 저장
- `GET /api/pipelines/{pipeline_id}` - 파이프라인 조회
- `GET /api/pipelines/project/{project_id}` - 프로젝트별 파이프라인 목록

### 코드 스타일
- Python 3.10+
- Type hints 필수
- Async/await 활용 (FastAPI)
- Pydantic v2 for validation

### 커밋 메시지
```
feat: 새로운 기능 추가
fix: 버그 수정
refactor: 코드 리팩토링
docs: 문서 수정
test: 테스트 추가
chore: 빌드, 의존성 관리
```

---

## 🔐 Permissions

### ✅ 자동 허용 (Explicit Permission 불필요)

**코드 작업:**
- ✅ Python 파일 읽기/쓰기 (`app/`)
- ✅ 모델, 스키마, 서비스, 라우터 수정
- ✅ 테스트 작성 및 실행 (pytest)
- ✅ 로그 확인 및 디버깅
- ✅ 로컬 테스트 (단위 테스트, 통합 테스트)

**개발 도구:**
- ✅ `pip install` (requirements.txt 기반)
- ✅ `git status`, `git diff`, `git log`
- ✅ 로컬 서버 실행 (uvicorn)
- ✅ 환경변수 설정 (.env 파일)

**데이터 작업:**
- ✅ SQLite 수정 (개발용 DB)
- ✅ 로컬 테스트 데이터 생성/삭제

---

### ⚠️ 명시적 Permission 필수

**Git 작업:**
- 🔐 **`git commit` 생성** - 사용자 승인 필수
- 🔐 **`git push`** - 사용자 승인 필수
- 🔐 **`git reset --hard` 등 파괴적 명령어** - 사용자 승인 필수

**데이터베이스 작업:**
- 🔐 **`fitai.db` 파일 삭제** (테이블 재생성) - 사용자 승인 필수
- 🔐 **스키마 변경** (새로운 컬럼 추가/삭제) - 사용자 승인 필수
  - PipelineStep에 새로운 필드 추가 시
  - 기존 필드 삭제/타입 변경 시

**API 호출:**
- 🔐 **Spring 서버로 API 요청** - 의도를 명확히 한 후
  - Pipeline 저장 후 Spring 서버에 Issue 생성 요청
  - 프로젝트 정보 조회

**의존성 관리:**
- 🔐 **새로운 라이브러리 추가** - 사용자 승인 필수
  - `pip install newlib` 후 `requirements.txt` 수정

**서버 관리:**
- 🔐 **프로덕션 서버 재시작** - 사용자 승인 필수
- 🔐 **DB 마이그레이션** - 사용자 승인 필수

---

## 🔧 Hooks & Automation

### 1️⃣ `on-pipeline-generated` Hook
**언제 실행:** 파이프라인이 생성되어 DB에 저장된 후

**실행 작업:**
```bash
# 1. 자동 테스트 실행
pytest app/tests/ -v

# 2. 생성된 파이프라인 통계 출력
echo "✅ Pipeline generated:"
echo "  - project_id: {project_id}"
echo "  - steps: {total_steps}"
echo "  - category: {category}"

# 3. Spring 서버에 POST 요청 (선택)
# curl -X POST http://localhost:8080/api/pipelines/sync \
#   -H "Content-Type: application/json" \
#   -d '{"pipeline_id": {pipeline_id}, "project_id": {project_id}}'

# 4. 결과 로깅
echo "✅ Pipeline sync completed"
```

---

### 2️⃣ `on-commit-prepare` Hook
**언제 실행:** `git commit` 준비 시 (코드 검증)

**실행 작업:**
```bash
# 1. 코드 포매팅
black app/ --line-length=100
isort app/

# 2. 문법 체크
flake8 app/ --max-line-length=100 --exclude=__pycache__

# 3. 타입 체크
mypy app/ --ignore-missing-imports

# 4. 테스트 실행
pytest app/tests/ --tb=short -q

# 실패 시 커밋 중단
if [ $? -ne 0 ]; then
  echo "❌ Code quality check failed. Commit cancelled."
  exit 1
fi

echo "✅ All checks passed. Ready to commit."
```

---

### 3️⃣ `on-test-failure` Hook
**언제 실행:** 테스트 실패 시

**실행 작업:**
```bash
# 1. 실패한 테스트 정보 출력
echo "❌ Test Failed:"
echo "  - Test File: {test_file}"
echo "  - Error: {error_message}"

# 2. 관련 코드 파일 제시
echo "\n📄 Related Files:"
grep -r "def {test_name}" app/tests/ --include="*.py"

# 3. 디버깅 정보
echo "\n🐛 Debug Info:"
echo "  - Coverage Report:"
pytest app/tests/ --cov=app --cov-report=term-missing

# 4. 사용자 피드백
echo "\n💡 Suggestions:"
echo "  - Check the error message above"
echo "  - Run: pytest app/tests/{test_file}::test_name -v"
```

---

### 4️⃣ `on-dependency-change` Hook
**언제 실행:** `requirements.txt` 파일이 변경된 후

**실행 작업:**
```bash
# 1. 새로운 의존성 설치
pip install -r requirements.txt

# 2. 호환성 테스트
python -c "
import sys
try:
    import fastapi
    import langchain
    import sqlalchemy
    import docling
    print('✅ All dependencies imported successfully')
except ImportError as e:
    print(f'❌ Dependency error: {e}')
    sys.exit(1)
"

# 3. 라이선스 확인 (선택)
pip-audit --desc

# 4. 버전 정보 로깅
echo "📦 Installed Versions:"
pip list | grep -E "fastapi|sqlalchemy|langchain|docling|openai"
```

---

### 5️⃣ `on-db-schema-change` Hook
**언제 실행:** `models/db/pipeline.py`가 수정된 후

**실행 작용:**
```bash
# 1. 스키마 변경 감지
echo "⚠️ Database schema may have changed"

# 2. 로컬 DB 리셋 제안
echo "💡 To apply changes to local development:"
echo "  rm fitai.db  # (또는 기존 DB 백업)"
echo "  # App 재시작 시 init_db()가 새 스키마로 테이블 생성"

# 3. 마이그레이션 필요 체크
if grep -q "new_column\|drop_column\|alter" <<< "$(git diff HEAD)"; then
  echo "⚠️ Breaking schema changes detected!"
  echo "  - 기존 데이터가 손실될 수 있습니다"
  echo "  - 사용자에게 승인을 요청하세요"
  exit 1
fi

echo "✅ Schema change check completed"
```

---

### 6️⃣ `on-file-change` Hook
**언제 실행:** 특정 파일이 수정될 때 (선택적 알림)

| 파일 | 실행 작업 |
|------|---------|
| `app/graph/pipeline_graph.py` | ➡️ LangGraph 테스트 실행 |
| `app/models/` | ➡️ 타입 체크 (mypy) |
| `app/routers/` | ➡️ API 엔드포인트 검증 |
| `.env` | ➡️ 환경변수 검증 (API 키 등) |
| `requirements.txt` | ➡️ 의존성 설치 및 호환성 테스트 |

---

### 설정 예시 (`.claude/hooks.json`)
```json
{
  "hooks": {
    "on-pipeline-generated": {
      "enabled": true,
      "commands": [
        "pytest app/tests/ -v",
        "echo '✅ Pipeline generated and tested'"
      ]
    },
    "on-commit-prepare": {
      "enabled": true,
      "commands": [
        "black app/ --line-length=100",
        "isort app/",
        "flake8 app/ --max-line-length=100"
      ]
    },
    "on-test-failure": {
      "enabled": true,
      "commands": [
        "echo '❌ Test failed. See details above.'"
      ]
    }
  }
}
```

---

## 🚀 Quick Start

### 1. 환경 설정
```bash
cd /Users/myeongsung/Documents/fitai
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경 변수 설정
```bash
cat > .env << EOF
OPENAI_API_KEY=sk-proj-your-key-here
DATABASE_URL=sqlite+aiosqlite:///./fitai.db
DEBUG=True
EOF
```

### 3. 서버 시작
```bash
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. API 테스트
```bash
curl -X POST http://localhost:8000/api/pipelines/generate-and-save \
  -F "project_id=1" \
  -F "category=BE" \
  -F "requirements=FastAPI 백엔드 개발" \
  -F "prd_file=@/path/to/proposal.pdf"
```

---

## 📞 Contact & Support

- **프로젝트 리드**: 김명성 (202145802)
- **협력자**: 이병찬
- **지도교수**: 김영인
- **기술 문의**: Claude Code Assistant

---

## 📝 Changelog

### 2026-04-13
- ✅ PipelineItem 모델에 `duration` 필드 추가
- ✅ PipelineStep(DB)에 `duration` 컬럼 추가
- ✅ LangGraph 5-Node 워크플로우 구현
- ✅ MSA 아키텍처 기초 설계

---

## ⚙️ Spring ↔ FastAPI 통신 예시

### Spring에서 FastAPI 호출 (RestClient)

```java
// Spring Controller에서 파이프라인 생성 요청
@PostMapping("/projects/{projectId}/pipelines/generate")
public ResponseEntity<?> generatePipeline(
    @PathVariable Long projectId,
    @RequestPart("requirements") String requirements,
    @RequestPart("category") String category,
    @RequestPart("pdfFile") MultipartFile pdfFile
) {
    // 1. PDF를 Python 서버에 전송
    MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
    body.add("project_id", projectId);
    body.add("requirements", requirements);
    body.add("category", category);
    body.add("prd_file", new FileSystemResource(pdfFile));

    // 2. FastAPI /api/pipelines/generate-and-save 호출
    ResponseEntity<PipelineResponse> response = restClient.post()
        .uri("http://localhost:8000/api/pipelines/generate-and-save")
        .contentType(MediaType.MULTIPART_FORM_DATA)
        .body(body)
        .retrieve()
        .toEntity(PipelineResponse.class);

    // 3. 응답받은 파이프라인을 issues로 변환
    PipelineResponse pipeline = response.getBody();
    for (PipelineStep step : pipeline.getSteps()) {
        Issue issue = Issue.builder()
            .title(step.getTitle())
            .description(step.getDescription())
            .duration(step.getDuration())
            .pipelineStepId(step.getId())  // Logical FK 설정
            .status("TODO")
            .build();
        issueRepository.save(issue);
    }

    return ResponseEntity.ok(pipeline);
}
```

---

## 📞 팀 정보

| 역할 | 이름 | 학번 | 담당 |
|------|------|------|------|
| 팀장 / BE | 김명성 | 202145802 | FastAPI, LangGraph, DB 설계 |
| 팀원 / 공동 | 이병찬 | (미기입) | Spring 서버, GitHub 연동 |
| 지도교수 | 김영인 | - | 프로젝트 지도 |

---

## 🔗 중요 리소스

### 외부 API
- **OpenAI GPT-4o**: https://platform.openai.com (API 키 필수)
- **GitHub API**: https://docs.github.com/en/rest (토큰 필수)

### 주요 라이브러리
- **FastAPI**: https://fastapi.tiangolo.com
- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **SQLAlchemy**: https://docs.sqlalchemy.org/
- **Docling**: https://ds4sd.github.io/docling/

### 개발 환경
- **Python**: 3.10+
- **FastAPI**: async/await 기반
- **Database**: SQLite (개발) / PostgreSQL (프로덕션)

---

## 📝 Changelog

### 2026-04-13 (최신)
- ✅ MSA 아키텍처 정의 (Spring + FastAPI 독립 DB)
- ✅ Logical FK 개념 도입 (물리적 외래키 없음)
- ✅ Permission 상세 정의
- ✅ Hook 6가지 시나리오 정의
- ✅ CLAUDE.md 작성 완료
- ✅ PipelineItem에 `duration` 필드 추가
- ✅ PipelineStep(DB)에 `duration`, `phase`, `tech_stack`, `acceptance_criteria` 컬럼 추가
- ✅ LangGraph 5-Node 워크플로우 구현

---

**마지막 수정**: 2026-04-13
**상태**: 🟢 활성 개발 중

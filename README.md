# fitai — AI Pipeline Design Service

PRD PDF와 기획자 요구사항을 입력받아 **LangGraph 기반 AI**가 프로젝트 전체 파이프라인을 설계합니다.

## 기술 스택

| 항목 | 선택 |
|------|------|
| Web Framework | FastAPI |
| AI Workflow | LangGraph |
| LLM | OpenAI GPT-4o |
| PDF Parsing | Docling |
| Validation | Pydantic v2 |

## 프로젝트 구조

```
fitai/
├── app/
│   ├── main.py             # FastAPI 앱 진입점
│   ├── config.py           # 환경변수 설정
│   ├── models/
│   │   └── pipeline.py     # Pydantic 데이터 모델
│   ├── graph/
│   │   └── pipeline_graph.py  # LangGraph 워크플로우 (핵심)
│   └── routers/
│       └── pipeline.py     # POST /pipeline/generate 엔드포인트
├── requirements.txt
├── .env.example
└── README.md
```

## LangGraph 워크플로우

```
PDF 파싱 (Docling)
    ↓
PRD 이해/요약 (GPT-4o)
    ↓
도메인 영역 식별 (GPT-4o)
    ↓
파이프라인 아이템 생성 (GPT-4o)
    ↓
우선순위 정렬 (HIGH → MEDIUM → LOW)
    ↓
JSON 응답 반환
```

## 빠른 시작

### 1. 환경변수 설정

```bash
cp .env.example .env
# .env 파일에 OPENAI_API_KEY 입력
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 서버 실행

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Swagger UI로 테스트

브라우저에서 http://localhost:8000/docs 접속

## API

### `POST /pipeline/generate`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `requirements` | `string` (form) | ✅ | 기획자 요구사항 텍스트 |
| `prd_file` | `file` (PDF) | ❌ | PRD PDF 파일 |

**Response**

```json
{
  "pipeline": [
    {
      "title": "사용자 인증 시스템",
      "priority": 1,
      "details": [
        "GitHub OAuth2 인증 플로우 구현",
        "JWT 발급/검증 미들웨어",
        "RefreshToken 관리",
        "로그아웃 처리"
      ]
    }
  ],
  "total_count": 1
}
```

## Phase 2 (예정)

- 기획자·개발자 컨펌 UI
- Fithub Spring Boot 연동 (OpenFeign)
- 파이프라인 아이템 → GitHub Issue 자동 생성

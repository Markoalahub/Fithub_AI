"""
Backend Technology Stack Templates

각 백엔드 프레임워크별 개발 파이프라인 템플릿
- Phase 1: 초기 설정 (1회만)
- Phase 2: 기반 구조 (1회만)
- Phase 3~N: 도메인별 반복 (각 도메인마다)
"""

# ──────────────────────────────────────────────
# Spring Boot Template
# ──────────────────────────────────────────────

SPRING_BOOT_TEMPLATE = {
    "name": "Spring Boot 백엔드",
    "description": "Spring Boot 3.x 기반 REST API 개발",
    "phases": [
        {
            "phase_num": 1,
            "name": "초기 설정",
            "type": "setup",  # 1회만 실행
            "steps": [
                {
                    "title": "Spring Initializr 프로젝트 생성",
                    "description": "Spring Boot 프로젝트 초기 구성",
                    "checklist": [
                        "Spring Initializr에서 프로젝트 생성 (Java 17+, Gradle/Maven)",
                        "필수 의존성 추가: Web, Data JPA, Lombok",
                        "DB 드라이버 추가 (PostgreSQL/MySQL/H2)",
                        "프로젝트 빌드 및 실행 테스트",
                    ]
                },
                {
                    "title": "application.yml 기본 설정",
                    "description": "프로젝트 기본 설정 파일 구성",
                    "checklist": [
                        "DB 연결 정보 설정 (datasource url, username, password)",
                        "JPA 설정 (hibernate.ddl-auto, show-sql, format-sql)",
                        "로깅 레벨 설정 (INFO, DEBUG)",
                        "포트 설정 (기본 8080 또는 다른 포트)",
                        ".env 파일로 민감 정보 관리",
                    ]
                }
            ]
        },
        {
            "phase_num": 2,
            "name": "기반 구조",
            "type": "infrastructure",  # 1회만 실행
            "steps": [
                {
                    "title": "DDD 기반 폴더 구조",
                    "description": "프로젝트 패키지 구조 설계",
                    "checklist": [
                        "com.project.domain 패키지 생성",
                        "각 도메인별 패키지 분리 (예: user, auth, payment)",
                        "도메인 내에서 controller, service, dto, repository, entity 서브패키지 생성",
                        "공용 패키지 생성 (config, util, exception, interceptor)",
                        "resources 폴더 구조 정리 (templates, static, db/migration)",
                    ]
                },
                {
                    "title": "글로벌 예외 처리",
                    "description": "ControllerAdvice 기반 예외 처리 전략",
                    "checklist": [
                        "도메인 에러 코드 열거형 정의 (예: USER_NOT_FOUND, INVALID_TOKEN)",
                        "글로벌 Exception Handler (ControllerAdvice) 구현",
                        "CustomException 추상 클래스 정의",
                        "에러 응답 포맷 표준화 (code, message, data, timestamp)",
                        "4xx, 5xx 에러별 처리 로직 구현",
                    ]
                },
                {
                    "title": "AOP 로깅 설정",
                    "description": "횡단 관심사 기반 로깅 구현",
                    "checklist": [
                        "@Aspect 기반 로깅 AOP 클래스 구현",
                        "Service 레이어 메서드 실행 시간 측정 로깅",
                        "메서드 입력값, 출력값 로깅",
                        "예외 발생 시 스택트레이스 로깅",
                        "로그 포맷 정의 (pattern, level, appender)",
                    ]
                },
                {
                    "title": "Swagger/OpenAPI 설정",
                    "description": "API 문서 자동 생성 설정",
                    "checklist": [
                        "springdoc-openapi-starter-webmvc-ui 의존성 추가",
                        "@OpenAPIDefinition으로 기본 문서 정보 설정 (제목, 버전, 설명)",
                        "Swagger UI 접근 경로 설정 (/api-docs, /swagger-ui.html)",
                        "인증 스키마 정의 (Bearer Token, API Key)",
                    ]
                },
                {
                    "title": "CI/CD 파이프라인",
                    "description": "GitHub Actions 기반 자동화",
                    "checklist": [
                        ".github/workflows/build.yml 작성 (빌드, 테스트, 린트)",
                        "Docker 이미지 빌드 (Dockerfile, .dockerignore)",
                        "ECR/Docker Hub 푸시 설정",
                        "배포 대상 설정 (EC2, ECS, K8s 중 선택)",
                        "환경별 배포 스크립트 작성 (dev, staging, prod)",
                    ]
                }
            ]
        },
        {
            "phase_num": 3,
            "name": "도메인별 개발 (반복)",
            "type": "domain",  # 각 도메인마다 반복
            "template_steps": [
                {
                    "title": "데이터 모델링 및 Entity 설계",
                    "description": "[도메인명] Entity 및 관계 정의",
                    "checklist": [
                        "[도메인명] Entity 클래스 생성 (@Entity, @Table)",
                        "PK, FK, 인덱스 설정 (@Id, @GeneratedValue, @ForeignKey)",
                        "다른 Entity와의 관계 설정 (@OneToMany, @ManyToOne, @OneToOne, @ManyToMany)",
                        "Entity 유효성 검증 (@NotNull, @NotBlank, @Email 등)",
                        "BaseEntity (생성일, 수정일) 상속 구조 정의",
                    ]
                },
                {
                    "title": "Repository 구현",
                    "description": "[도메인명] 데이터 접근 계층",
                    "checklist": [
                        "[도메인명]Repository 인터페이스 생성 (JpaRepository 상속)",
                        "필요한 커스텀 쿼리 메서드 정의 (findByXxx, findAllByXxx 등)",
                        "@Query로 복잡한 JPQL/SQL 작성 (필요시)",
                        "페이징 및 정렬 처리 (Pageable, Page<T>)",
                        "벌크 연산 메서드 정의 (deleteByXxx, updateByXxx)",
                    ]
                },
                {
                    "title": "Service 구현",
                    "description": "[도메인명] 비즈니스 로직 계층",
                    "checklist": [
                        "[도메인명]Service 클래스 생성 (@Service, @Transactional)",
                        "Create, Read, Update, Delete 메서드 구현",
                        "비즈니스 유효성 검사 로직 구현 (예: 중복 체크, 권한 검증)",
                        "도메인 예외 발생 (@throw [도메인]Exception)",
                        "@Transactional readOnly 속성 적절히 설정",
                    ]
                },
                {
                    "title": "DTO 정의",
                    "description": "[도메인명] 요청/응답 데이터 구조",
                    "checklist": [
                        "[도메인명]CreateRequest DTO 정의 (필드 검증 어노테이션 포함)",
                        "[도메인명]UpdateRequest DTO 정의",
                        "[도메인명]Response DTO 정의 (응답에 필요한 필드만)",
                        "DTO ↔ Entity 매핑 (MapStruct 또는 생성자 활용)",
                        "민감 정보 필터링 (password, secret 등 제외)",
                    ]
                },
                {
                    "title": "Controller 및 API 엔드포인트",
                    "description": "[도메인명] REST API 노출",
                    "checklist": [
                        "[도메인명]Controller 클래스 생성 (@RestController, @RequestMapping)",
                        "POST, GET, PUT/PATCH, DELETE 엔드포인트 구현",
                        "요청/응답 DTO 바인딩 (@RequestBody, @RequestParam, @PathVariable)",
                        "HTTP 상태 코드 적절히 설정 (201, 204, 400, 404, 500 등)",
                        "@ApiOperation, @ApiResponse로 Swagger 문서화",
                    ]
                },
                {
                    "title": "검증 및 테스트",
                    "description": "[도메인명] 단위/통합 테스트",
                    "checklist": [
                        "[도메인명]ServiceTest 작성 (@SpringBootTest 또는 @DataJpaTest)",
                        "Happy path 및 Exception 케이스 테스트",
                        "[도메인명]ControllerTest 작성 (MockMvc, @WebMvcTest)",
                        "API 엔드포인트 응답 검증 (상태 코드, JSON 형식)",
                        "테스트 커버리지 80% 이상 달성 (JaCoCo)",
                    ]
                }
            ]
        }
    ]
}


# ──────────────────────────────────────────────
# FastAPI Template (추후 추가)
# ──────────────────────────────────────────────

FASTAPI_TEMPLATE = {
    "name": "FastAPI 백엔드",
    "description": "FastAPI 기반 REST API 개발",
    # TODO: 상세 구조 정의
}


# ──────────────────────────────────────────────
# React Template
# ──────────────────────────────────────────────

REACT_TEMPLATE = {
    "name": "React 프론트엔드",
    "description": "React 18+ 기반 웹 애플리케이션",
    "phases": [
        {
            "phase_num": 1,
            "name": "초기 설정",
            "type": "setup",
            "steps": [
                {
                    "title": "Vite 기반 React 프로젝트 생성",
                    "description": "React 개발 환경 구축",
                    "checklist": [
                        "npm create vite@latest [project-name] -- --template react-ts",
                        "TypeScript, ESLint, Prettier 설정",
                        "필수 라이브러리 설치 (React Router, Axios, Zustand/Redux)",
                        "Tailwind CSS 또는 CSS-in-JS (Styled-components/Emotion) 설정",
                        "개발 서버 실행 테스트 (npm run dev)",
                    ]
                },
                {
                    "title": ".env 및 설정 파일",
                    "description": "환경 변수 및 앱 설정",
                    "checklist": [
                        ".env.local, .env.dev, .env.prod 파일 생성",
                        "API 베이스 URL, 타임아웃, 재시도 정책 설정",
                        "tsconfig.json에서 path alias 설정 (@components, @hooks, @utils 등)",
                        "vite.config.ts에서 플러그인 및 최적화 설정",
                    ]
                }
            ]
        },
        {
            "phase_num": 2,
            "name": "기반 구조",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "폴더 구조 및 레이어 설계",
                    "description": "프로젝트 디렉토리 구조",
                    "checklist": [
                        "src/pages (페이지 컴포넌트)",
                        "src/components (재사용 가능한 컴포넌트)",
                        "src/hooks (커스텀 훅)",
                        "src/stores (전역 상태 관리)",
                        "src/apis (API 클라이언트)",
                        "src/types (TypeScript 타입 정의)",
                        "src/utils (유틸리티 함수)",
                        "src/assets (이미지, 폰트 등)",
                    ]
                },
                {
                    "title": "라우팅 설정",
                    "description": "React Router 기반 네비게이션",
                    "checklist": [
                        "React Router 설정 (Routes, Route, useNavigate)",
                        "레이아웃 구조 정의 (Layout, Header, Footer, Sidebar)",
                        "보호된 라우트 구현 (PrivateRoute)",
                        "404 Not Found 페이지",
                        "라우트별 권한 검증 (권한 가드)",
                    ]
                },
                {
                    "title": "API 클라이언트 설정",
                    "description": "Axios 또는 Fetch 기반 API 통신",
                    "checklist": [
                        "API 인스턴스 생성 (baseURL, timeout, interceptor)",
                        "요청/응답 인터셉터 설정 (토큰 주입, 에러 처리)",
                        "에러 처리 전략 (401, 403, 500 등)",
                        "API 호출 유틸리티 함수 (useQuery, useMutation 래퍼)",
                    ]
                },
                {
                    "title": "전역 상태 관리",
                    "description": "Zustand/Redux 기반 상태 관리",
                    "checklist": [
                        "상태 스토어 구조 정의 (auth, user, ui 등)",
                        "액션 및 리듀서 구현",
                        "미들웨어 설정 (필요시: Redux-Thunk, Redux-Saga)",
                        "DevTools 연동 (Redux DevTools, Zustand DevTools)",
                    ]
                }
            ]
        }
        # Phase 3~N은 도메인별로 동적 생성
    ]
}


# ──────────────────────────────────────────────
# DevOps Template
# ──────────────────────────────────────────────

DEVOPS_TEMPLATE = {
    "name": "DevOps",
    "description": "인프라, CI/CD, 모니터링 구축",
    "phases": [
        {
            "phase_num": 1,
            "name": "CI/CD 파이프라인",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "GitHub Actions 워크플로우 설정",
                    "description": "자동 빌드, 테스트, 배포 파이프라인",
                    "checklist": [
                        ".github/workflows/ci.yml 작성 (테스트, 린트)",
                        "브랜ch 전략 정의 (main, develop, feature branches)",
                        "PR 체크 설정 (필수 검사 통과 후 merge)",
                        "자동 테스트 커버리지 체크 (최소 80%)",
                        "빌드 실패 시 알림 설정",
                    ]
                },
                {
                    "title": "배포 파이프라인",
                    "description": "자동 배포 프로세스",
                    "checklist": [
                        ".github/workflows/deploy.yml 작성",
                        "환경별 배포 스크립트 (dev, staging, prod)",
                        "배포 전 smoke test 자동화",
                        "롤백 전략 정의",
                        "배포 로그 수집 및 저장",
                    ]
                }
            ]
        },
        {
            "phase_num": 2,
            "name": "컨테이너화 및 오케스트레이션",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "Docker 설정",
                    "description": "애플리케이션 컨테이너화",
                    "checklist": [
                        "Dockerfile 작성 (멀티스테이지 빌드)",
                        ".dockerignore 설정",
                        "docker-compose.yml 설정 (로컬 개발)",
                        "Docker 이미지 태깅 및 버저닝 전략",
                        "이미지 스캔 및 보안 검사 (Trivy)",
                    ]
                },
                {
                    "title": "Kubernetes 또는 ECS 설정",
                    "description": "오케스트레이션 플랫폼 구성",
                    "checklist": [
                        "배포 대상 선택 (K8s, ECS, EC2)",
                        "K8s의 경우: Deployment, Service, Ingress 설정",
                        "resource limits 및 requests 정의",
                        "헬스 체크 (liveness, readiness probe)",
                        "스케일링 정책 설정 (HPA, auto-scaling)",
                    ]
                }
            ]
        },
        {
            "phase_num": 3,
            "name": "모니터링 및 로깅",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "메트릭 수집 및 시각화",
                    "description": "Prometheus + Grafana 모니터링",
                    "checklist": [
                        "Prometheus 설정 (스크래이핑 설정, 리텐션)",
                        "애플리케이션 메트릭 노출 (actuator endpoint)",
                        "Grafana 대시보드 구성 (CPU, 메모리, 응답시간)",
                        "알림 규칙 정의 (CPU > 80%, 응답시간 > 1초)",
                        "Alertmanager 설정 (이메일, Slack 알림)",
                    ]
                },
                {
                    "title": "로그 수집 및 분석",
                    "description": "ELK 또는 Loki 기반 로깅",
                    "checklist": [
                        "로그 수집 설정 (Fluentd, Logstash 또는 Promtail)",
                        "Elasticsearch 또는 Loki 설정",
                        "Kibana 또는 Grafana Loki 대시보드 구성",
                        "로그 검색 및 필터링 쿼리 작성",
                        "로그 리텐션 정책 설정",
                    ]
                }
            ]
        },
        {
            "phase_num": 4,
            "name": "보안 및 최적화",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "인프라 보안",
                    "description": "보안 설정 및 hardening",
                    "checklist": [
                        "네트워크 보안 그룹 설정 (포트, IP 화이트리스트)",
                        "SSL/TLS 인증서 설정 (Let's Encrypt)",
                        "비밀정보 관리 (AWS Secrets Manager, HashiCorp Vault)",
                        "IAM 권한 설정 (최소 권한 원칙)",
                        "정기적인 보안 감사 및 취약점 검사",
                    ]
                },
                {
                    "title": "성능 최적화",
                    "description": "배포 및 런타임 최적화",
                    "checklist": [
                        "CDN 설정 (CloudFront, Cloudflare 등)",
                        "DB 쿼리 최적화 및 인덱싱",
                        "캐싱 전략 (Redis, Memcached)",
                        "부하 테스트 및 병목 분석",
                        "비용 최적화 (리소스 우리타이징)",
                    ]
                }
            ]
        }
    ]
}


# ──────────────────────────────────────────────
# AI Engineer Template
# ──────────────────────────────────────────────

AI_ENGINEER_TEMPLATE = {
    "name": "AI Engineer",
    "description": "머신러닝 모델 개발 및 배포",
    "phases": [
        {
            "phase_num": 1,
            "name": "데이터 수집 및 전처리",
            "type": "setup",
            "steps": [
                {
                    "title": "데이터 수집",
                    "description": "학습 데이터 수집 및 EDA",
                    "checklist": [
                        "데이터 소스 확인 (API, DB, 파일)",
                        "데이터 수집 스크립트 작성",
                        "EDA (Exploratory Data Analysis) 수행",
                        "데이터 통계 분석 (분포, 이상값, 결측치)",
                        "데이터 버전 관리 (DVC 또는 S3)",
                    ]
                },
                {
                    "title": "데이터 전처리 및 feature engineering",
                    "description": "모델 학습을 위한 데이터 준비",
                    "checklist": [
                        "결측치 처리 (imputation, removal)",
                        "아웃라이어 감지 및 처리",
                        "데이터 정규화/표준화 (scaling, encoding)",
                        "feature 엔지니어링 (파생 변수 생성)",
                        "train/validation/test split (예: 70/15/15)",
                    ]
                }
            ]
        },
        {
            "phase_num": 2,
            "name": "모델 설계 및 구현",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "모델 선택 및 베이스라인",
                    "description": "적절한 모델 아키텍처 선택",
                    "checklist": [
                        "문제 정의 (분류/회귀/클러스터링/NLP/Vision)",
                        "베이스라인 모델 선택 (Logistic Regression, Decision Tree 등)",
                        "베이스라인 성능 측정",
                        "고도화 모델 후보 선정 (XGBoost, Neural Network, Transformer 등)",
                        "모델 비교 실험 계획 수립",
                    ]
                },
                {
                    "title": "모델 구현",
                    "description": "선택된 모델 코드 작성",
                    "checklist": [
                        "모델 클래스 정의 (Scikit-learn, PyTorch, TensorFlow)",
                        "하이퍼파라미터 설정",
                        "모델 학습 코드 작성",
                        "모델 저장/로드 함수 구현",
                        "코드 리뷰 및 리팩토링",
                    ]
                }
            ]
        },
        {
            "phase_num": 3,
            "name": "모델 학습 및 평가",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "모델 학습",
                    "description": "데이터로 모델 학습",
                    "checklist": [
                        "학습 실행 (epoch, batch size, learning rate 설정)",
                        "학습 곡선 모니터링 (loss, accuracy)",
                        "조기 종료 (Early Stopping) 적용",
                        "체크포인트 저장 (best model)",
                        "학습 로그 기록 (MLflow, Weights & Biases)",
                    ]
                },
                {
                    "title": "모델 평가 및 검증",
                    "description": "학습된 모델 성능 평가",
                    "checklist": [
                        "테스트 셋 평가 (정확도, 정밀도, 재현율, F1-score)",
                        "혼동 행렬 분석",
                        "Cross-validation 수행",
                        "Ablation study (feature 중요도 분석)",
                        "에러 분석 및 개선 영역 도출",
                    ]
                }
            ]
        },
        {
            "phase_num": 4,
            "name": "모델 최적화 및 배포",
            "type": "infrastructure",
            "steps": [
                {
                    "title": "하이퍼파라미터 최적화",
                    "description": "GridSearch/RandomSearch를 통한 튜닝",
                    "checklist": [
                        "하이퍼파라미터 서치 스페이스 정의",
                        "GridSearch 또는 RandomSearch 실행",
                        "Bayesian Optimization 고려",
                        "최적 파라미터 선정",
                        "최적화된 모델 재학습",
                    ]
                },
                {
                    "title": "모델 배포",
                    "description": "모델 프로덕션화",
                    "checklist": [
                        "모델 포맷 변환 (ONNX, SavedModel, TorchScript 등)",
                        "모델 서빙 서버 구축 (FastAPI, Flask, TFServing)",
                        "예측 API 엔드포인트 구현",
                        "배치 예측 파이프라인 (스케줄러)",
                        "모니터링 및 성능 추적 (모델 드리프트 감지)",
                    ]
                }
            ]
        }
    ]
}


# ──────────────────────────────────────────────
# Template Registry
# ──────────────────────────────────────────────

BACKEND_TEMPLATES = {
    "Spring": SPRING_BOOT_TEMPLATE,
    "FastAPI": FASTAPI_TEMPLATE,
}

FRONTEND_TEMPLATES = {
    "React": REACT_TEMPLATE,
}

DEVOPS_TEMPLATES = {
    "DevOps": DEVOPS_TEMPLATE,
}

AI_TEMPLATES = {
    "AI": AI_ENGINEER_TEMPLATE,
}

ALL_TEMPLATES = {
    **BACKEND_TEMPLATES,
    **FRONTEND_TEMPLATES,
    **DEVOPS_TEMPLATES,
    **AI_TEMPLATES,
}

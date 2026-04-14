"""
파이프라인 품질 평가 시스템 (LLM as Judge)

Langsmith를 통해 평가 프로세스를 추적하고,
생성된 파이프라인의 품질을 정량화합니다.

평가 항목:
1. Phase 구조 준수 (0-25점)
   - Phase 1, 2, 3+ 명확히 분리되었는가?

2. Step 크기 적절성 (0-25점)
   - 각 step이 1-2시간 단위인가?
   - 너무 크지는 않은가?

3. 구체성 (0-25점)
   - details가 충분히 구체적인가?
   - 기술 스펙이 포함되어 있는가?

4. 논리적 흐름 (0-25점)
   - 도메인 간 의존성이 합리적인가?
   - priority가 올바르게 설정되었는가?

합계: 0-100점
"""

import json
from typing import List, Dict, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


# ──────────────────────────────────────────────
# 평가 기준 (Rubric)
# ──────────────────────────────────────────────

EVALUATION_RUBRIC = {
    "phase_structure": {
        "name": "Phase 구조 준수",
        "max_score": 25,
        "criteria": [
            "Phase 1, 2, 3+ 명확하게 분리됨",
            "Phase 1, 2는 고정 (설정, 기반구조)",
            "Phase 3부터 도메인별 반복",
            "각 Phase의 목적이 명확함",
        ]
    },
    "step_size": {
        "name": "Step 크기 적절성",
        "max_score": 25,
        "criteria": [
            "각 step이 1-2시간 단위 추정",
            "Step이 너무 크지 않음 (하루 이상 작업 없음)",
            "Step이 너무 작지 않음 (15분 이하 작업 없음)",
            "Step 간 시간 추정이 일관성 있음",
        ]
    },
    "concreteness": {
        "name": "구체성 및 기술 깊이",
        "max_score": 25,
        "criteria": [
            "details가 4개 이상, 구체적임",
            "기술 스택/라이브러리 명시 (Spring, JPA, JWT 등)",
            "완료 기준이 명확함",
            "코드 레벨의 세부사항 포함",
        ]
    },
    "logical_flow": {
        "name": "논리적 흐름 및 우선순위",
        "max_score": 25,
        "criteria": [
            "도메인 간 의존성이 합리적",
            "priority 순서가 올바름",
            "선행 작업 후 후행 작업 진행",
            "도메인 식별이 정확함",
        ]
    }
}


# ──────────────────────────────────────────────
# LLM Judge
# ──────────────────────────────────────────────

class PipelineEvaluator:
    """파이프라인 평가기"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.2,  # 일관된 평가
        )

    def evaluate(
        self,
        category: str,
        items: List[Dict],
    ) -> Dict:
        """
        파이프라인 평가 (LangSmith 자동 추적)

        Args:
            category: 직군 (FE, BE, DevOps, AI)
            items: 파이프라인 아이템 리스트

        Returns:
            {
                "category": "BE",
                "total_score": 82,
                "scores": {
                    "phase_structure": 22,
                    "step_size": 20,
                    "concreteness": 23,
                    "logical_flow": 19,
                },
                "feedback": "...",
                "strengths": ["..."],
                "improvements": ["..."]
            }
        """
        # 1단계: 평가 항목별 점수 계산
        scores = self._evaluate_by_criteria(category, items)

        # 2단계: 피드백 생성
        feedback, strengths, improvements = self._generate_feedback(
            category, items, scores
        )

        # 3단계: 종합 점수 계산
        total_score = sum(scores.values())

        return {
            "category": category,
            "total_score": total_score,
            "max_score": 100,
            "scores": scores,
            "feedback": feedback,
            "strengths": strengths,
            "improvements": improvements,
        }

    def _evaluate_by_criteria(
        self,
        category: str,
        items: List[Dict],
    ) -> Dict[str, int]:
        """각 평가 기준별 점수 계산"""

        items_str = json.dumps(items, ensure_ascii=False, indent=2)

        msg = [
            SystemMessage(content=(
                "당신은 경험 많은 소프트웨어 아키텍트입니다.\n"
                "다음 평가 기준에 따라 생성된 파이프라인을 평가하세요.\n\n"
                "평가 기준:\n"
                f"{self._format_rubric()}"
            )),
            HumanMessage(content=(
                f"## 직군: {category}\n\n"
                f"## 생성된 파이프라인 Items:\n{items_str}\n\n"
                "다음 JSON 형식으로 각 기준별 점수를 매겨주세요:\n"
                """{"phase_structure": 20, "step_size": 18, "concreteness": 22, "logical_flow": 19}"""
            )),
        ]

        response = self.llm.invoke(msg)
        content = response.content.strip()

        # JSON 파싱
        if "{" in content:
            json_str = content[content.find("{"):content.rfind("}")+1]
            try:
                scores = json.loads(json_str)
                # 점수 정규화
                for key in scores:
                    max_score = EVALUATION_RUBRIC.get(key, {}).get("max_score", 25)
                    scores[key] = min(max(scores[key], 0), max_score)
                return scores
            except json.JSONDecodeError:
                pass

        # 기본값
        return {
            "phase_structure": 20,
            "step_size": 18,
            "concreteness": 20,
            "logical_flow": 18,
        }

    def _generate_feedback(
        self,
        category: str,
        items: List[Dict],
        scores: Dict[str, int],
    ) -> Tuple[str, List[str], List[str]]:
        """상세 피드백 생성"""

        items_str = json.dumps(items, ensure_ascii=False, indent=2)

        msg = [
            SystemMessage(content=(
                f"당신은 경험 많은 소프트웨어 아키텍트입니다.\n"
                f"다음 파이프라인을 분석하고, 강점과 개선점을 지적하세요.\n\n"
                f"점수 정보:\n{json.dumps(scores, ensure_ascii=False, indent=2)}"
            )),
            HumanMessage(content=(
                f"## 직군: {category}\n\n"
                f"## 파이프라인:\n{items_str}\n\n"
                "다음 JSON 형식으로 피드백을 작성하세요:\n"
                """{
  "feedback": "전반적인 평가 (2-3문장)",
  "strengths": ["강점1", "강점2", "강점3"],
  "improvements": ["개선점1", "개선점2", "개선점3"]
}"""
            )),
        ]

        response = self.llm.invoke(msg)
        content = response.content.strip()

        # JSON 파싱
        if "{" in content:
            json_str = content[content.find("{"):content.rfind("}")+1]
            try:
                data = json.loads(json_str)
                return (
                    data.get("feedback", ""),
                    data.get("strengths", []),
                    data.get("improvements", []),
                )
            except json.JSONDecodeError:
                pass

        return "평가 생성 실패", [], []

    def _format_rubric(self) -> str:
        """평가 기준 포맷팅"""
        result = []
        for key, criterion in EVALUATION_RUBRIC.items():
            result.append(f"\n### {criterion['name']} ({criterion['max_score']}점)")
            for c in criterion['criteria']:
                result.append(f"- {c}")
        return "\n".join(result)


# ──────────────────────────────────────────────
# 평가 결과 저장 및 추적 (Langsmith)
# ──────────────────────────────────────────────

def log_evaluation_to_langsmith(
    project_id: int,
    category: str,
    evaluation_result: Dict,
):
    """
    Langsmith에 평가 결과 기록
    (실제 구현 시 Langsmith API 사용)
    """
    # TODO: Langsmith 연동
    # from langsmith import Client
    # client = Client()
    # client.create_evaluation_result(...)
    pass


def get_evaluation_history(project_id: int) -> List[Dict]:
    """
    프로젝트의 평가 이력 조회
    (누적 점수, 개선 트렌드 분석)
    """
    # TODO: DB에서 평가 이력 조회
    pass


if __name__ == "__main__":
    # 테스트 (스탠드얼론 실행용)
    evaluator = PipelineEvaluator()

    test_items = [
        {
            "title": "데이터 모델링 및 Entity 설계",
            "description": "User Entity 클래스 생성 (@Entity, @Table)\nPK, FK, 인덱스 설정\nValidation 어노테이션 추가"
        },
        {
            "title": "Repository 구현",
            "description": "UserRepository 인터페이스 생성 (JpaRepository 상속)\n커스텀 쿼리 메서드 정의\n페이징 처리"
        }
    ]

    result = evaluator.evaluate("BE", test_items)
    print(json.dumps(result, ensure_ascii=False, indent=2))

"""
Template Loader - YAML 템플릿을 파이썬 객체로 로드
"""
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class TemplateStage(BaseModel):
    """템플릿 단계"""
    order: int
    title: str
    description: str
    key_points: List[str]


class PipelineTemplate(BaseModel):
    """파이프라인 템플릿"""
    framework: str
    name: str
    description: str
    tech_stack: List[str]
    stages: List[TemplateStage]


class TemplateLoader:
    """YAML 템플릿 로더"""

    def __init__(self):
        self.templates_dir = Path(__file__).parent.parent / "templates"
        self._cache: Dict[str, PipelineTemplate] = {}
        self._load_all_templates()

    def _load_all_templates(self) -> None:
        """모든 템플릿 로드"""
        for yaml_file in self.templates_dir.rglob("*.yaml"):
            framework = self._get_framework_from_path(yaml_file)
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    template = PipelineTemplate(**data)
                    self._cache[framework] = template
            except Exception as e:
                print(f"Failed to load template {yaml_file}: {e}")

    def _get_framework_from_path(self, path: Path) -> str:
        """경로에서 프레임워크 이름 추출 (spring_boot, react 등)"""
        return path.stem

    def get_template(self, framework: str) -> Optional[PipelineTemplate]:
        """특정 프레임워크 템플릿 가져오기"""
        return self._cache.get(framework)

    def get_all_frameworks(self) -> List[str]:
        """지원하는 모든 프레임워크 목록"""
        return list(self._cache.keys())

    def get_template_stages(self, framework: str) -> Optional[List[TemplateStage]]:
        """특정 프레임워크의 모든 스테이지 가져오기"""
        template = self.get_template(framework)
        return template.stages if template else None

    def get_stage_descriptions(self, framework: str) -> Optional[Dict[int, str]]:
        """프레임워크의 단계별 설명을 dict로 반환 (order → description)"""
        stages = self.get_template_stages(framework)
        if not stages:
            return None
        return {stage.order: stage.description for stage in stages}


# 싱글톤 인스턴스
template_loader = TemplateLoader()


# ──────────────────────────────────────────────
# 편의 함수
# ──────────────────────────────────────────────

def get_supported_frameworks() -> List[str]:
    """지원하는 모든 프레임워크 목록"""
    return template_loader.get_all_frameworks()


def get_template_for_framework(framework: str) -> Optional[PipelineTemplate]:
    """특정 프레임워크 템플릿"""
    return template_loader.get_template(framework)


def get_stage_descriptions_for_framework(framework: str) -> Optional[Dict[int, str]]:
    """프레임워크별 단계 설명"""
    return template_loader.get_stage_descriptions(framework)

import requests
import json
import time

BASE_URL = "http://localhost:8080/api/v1"

def print_section(title):
    print("\n" + "=" * 60)
    print(f"🌟 {title}")
    print("=" * 60)

def main():
    print("🚀 [서버 연동 통합 테스트 시작]")
    print("스프링 부트(Port 8080)와 FastAPI AI 엔진(Port 8000)이 구동 중인 상태에서 테스트를 실행합니다.\n")

    # -------------------------------------------------------------
    # 0. 프로젝트 생성 (Seed Data)
    # -------------------------------------------------------------
    print_section("0. 테스트용 프로젝트 생성")
    project_payload = {
        "name": "FitHub Fitness Recorder",
        "description": "사용자의 운동 루틴을 기록하고 주간 통계를 시각화하는 모바일 애플리케이션"
    }
    
    try:
        res = requests.post(f"{BASE_URL}/projects", json=project_payload)
        res.raise_for_status()
        project = res.json()
        project_id = project["id"]
        print(f"✅ 프로젝트 생성 완료! ID: {project_id}")
        print(json.dumps(project, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"❌ 프로젝트 생성 실패 (서버가 켜져 있는지 확인하세요): {e}")
        return

    # -------------------------------------------------------------
    # 1. Stage 1: 유저 플로우 세션 시작
    # -------------------------------------------------------------
    print_section("1. Stage 1: 유저 플로우 생성 및 기획 인터뷰 시작")
    requirements = (
        "운동 일지 등록 및 루틴 추천 기능. "
        "사용자가 당일 운동(유산소/무산소) 세트수와 무게를 기록하고, "
        "기록된 누적 운동 데이터를 주간 그래프로 대시보드에 노출해 주는 기능."
    )
    
    # generate-userflow는 multipart/form-data를 소모합니다.
    form_data = {
        "projectId": (None, str(project_id)),
        "requirements": (None, requirements),
        "techStack": (None, "Spring Boot, React Native")
    }
    
    print("⏳ AI 기획 분석 및 첫 질문 생성 중... (약 10~15초 소요)")
    try:
        res = requests.post(f"{BASE_URL}/pipelines/generate-userflow", files=form_data)
        res.raise_for_status()
        session = res.json()
        flow_id = session.get("flow_id")
        status = session.get("status")
        question = session.get("question")
        
        print(f"✅ 유저 플로우 인터뷰 세션이 생성되었습니다! Flow ID: {flow_id}")
        print(f"🤖 AI의 추가 기획 질문:")
        print(f"👉 \"{question}\"")
    except Exception as e:
        print(f"❌ Stage 1 (유저 플로우 세션 시작) 실패: {e}")
        return

    # -------------------------------------------------------------
    # 2. Stage 1 (계속): 기획자 답변 전송 및 플로우 확정 (confirm=True)
    # -------------------------------------------------------------
    print_section("2. Stage 1 (계속): 추가 질문 답변 및 유저 플로우 최종 확정")
    
    answer_text = "기본 제공 루틴 외에도 커스텀으로 자유롭게 등록할 수 있는 기능을 포함하고, 운동 기록 누락 방지를 위한 매일 저녁 9시 리마인드 푸시 알림도 희망합니다."
    
    print(f"✍️ 답변 내용: \"{answer_text}\"")
    print("⏳ AI 답변 검토 및 화면 흐름 설계(User Flow Nodes) 도출 중...")
    
    try:
        # answer 엔드포인트 호출
        params = {
            "answer": answer_text,
            "confirm": "true"  # 플로우를 강제 확정하고 다음 단계로 진입
        }
        res = requests.post(f"{BASE_URL}/pipelines/userflow-session/{flow_id}/answer", params=params)
        res.raise_for_status()
        confirmed_flow = res.json()
        
        print("✅ 유저 플로우 노드가 최종 확정되었습니다!")
        nodes = confirmed_flow.get("nodes", [])
        for node in nodes:
            print(f"  📍 [{node.get('sequence_order')}] {node.get('name')} (타입: {node.get('node_type')})")
            print(f"     └ 설명: {node.get('description')}")
    except Exception as e:
        print(f"❌ Stage 1 (인터뷰 답변 및 확정) 실패: {e}")
        return

    # -------------------------------------------------------------
    # 3. Stage 2: 유저 플로우 -> 와이어프레임 생성
    # -------------------------------------------------------------
    print_section("3. Stage 2: 각 화면별 ASCII UI 와이어프레임 생성")
    print(f"⏳ 유저 플로우 노드 ID {flow_id}에 대해 UI 와이어프레임 디자인을 렌더링 중...")
    
    try:
        params = {
            "userFlowId": flow_id
        }
        res = requests.post(f"{BASE_URL}/pipelines/generate-wireframe", params=params)
        res.raise_for_status()
        wireframe_res = res.json()
        
        print("✅ 화면별 Lo-Fi UI 와이어프레임 설계 완료!")
        nodes_with_wf = wireframe_res.get("nodes", [])
        for node in nodes_with_wf[:2]:  # 화면 공간을 위해 처음 2개 노드만 발췌 출력
            print(f"\n📱 [화면]: {node.get('name')}")
            print(f"📝 [화면 설명]: {node.get('description')}")
            print("🎨 [ASCII Layout]:")
            print(node.get("wireframe_ascii"))
    except Exception as e:
        print(f"❌ Stage 2 (와이어프레임 생성) 실패: {e}")
        return

    # -------------------------------------------------------------
    # 4. Stage 3: 개발 파이프라인 생성 (화면 연동 태스크 분해)
    # -------------------------------------------------------------
    print_section("4. Stage 3: 유저플로우/와이어프레임 매핑 백엔드(BE) 개발 파이프라인 태스크 도출")
    print("⏳ 화면 요소와 1:1 대응되는 데이터 모델 및 API 컨트롤러 태스크 자동 분해 중...")
    
    try:
        params = {
            "userFlowId": flow_id,
            "projectId": project_id,
            "category": "BE"
        }
        res = requests.post(f"{BASE_URL}/pipelines/generate-pipeline-from-flow", params=params)
        res.raise_for_status()
        pipeline_res = res.json()
        
        print("✅ 백엔드(BE) 개발 파이프라인 태스크 생성 및 DB 저장 완료!")
        steps = pipeline_res.get("steps", [])
        for i, step in enumerate(steps):
            print(f"\n🛠️ Task {i+1}: {step.get('title')}")
            print(f"   └ 상세 내용: {step.get('description')}")
            print(f"   └ 완료 상태: {'완료' if step.get('is_completed') else '대기 중'}")
            
    except Exception as e:
        print(f"❌ Stage 3 (파이프라인 태스크 도출) 실패: {e}")
        return

    print("\n" + "=" * 60)
    print("🎉 [모든 서버 연동 통합 테스트가 대성공으로 완료되었습니다!]")
    print("=" * 60)

if __name__ == "__main__":
    main()

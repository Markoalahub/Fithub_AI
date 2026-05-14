import asyncio
import httpx
import json
import time

async def test_pdf(filename):
    url_start = "http://127.0.0.1:8000/pipelines/generate-userflow"
    
    print(f"\n[{filename}] 인터뷰 세션 시작 중...")
    try:
        with open(filename, 'rb') as f:
            files = {'file': (filename, f, 'application/pdf')}
            data = {
                'project_id': 1,
                'requirements': f"{filename} 기반의 기획",
                'tech_stack': 'Spring Boot, React'
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url_start, data=data, files=files)
                if resp.status_code != 200:
                    return f"Failed to start: {resp.status_code} {resp.text}"
                
                result = resp.json()
                flow_id = result.get('flow_id')
                ai_message = result.get('ai_message', '')
                options = result.get('options', [])
                
                print(f"[{filename}] Flow ID: {flow_id} 발급됨. AI 제안 수신 (옵션 {len(options)}개)")
                
                # Turn 2: 첫 번째 제안 선택 후 확정
                url_answer = f"http://127.0.0.1:8000/pipelines/userflow-session/{flow_id}/answer"
                answer_data = {
                    'answer': '첫 번째 전략으로 진행해주세요.',
                    'confirm': 'true'
                }
                resp_ans = await client.post(url_answer, data=answer_data)
                if resp_ans.status_code != 200:
                    return f"Failed to answer: {resp_ans.status_code} {resp_ans.text}"
                
                ans_result = resp_ans.json()
                user_flow = ans_result.get('user_flow', {})
                nodes = len(user_flow.get('nodes', [])) if user_flow else 0
                edges = len(user_flow.get('edges', [])) if user_flow else 0
                
                print(f"[{filename}] 최종 확정 완료 - 생성된 노드: {nodes}개, 엣지: {edges}개")
                return {
                    "file": filename,
                    "flow_id": flow_id,
                    "ai_initial_reply": ai_message[:100] + "...",
                    "nodes": nodes,
                    "edges": edges
                }
    except Exception as e:
        return f"Exception: {str(e)}"

async def main():
    pdfs = ['t1.pdf', 't2.pdf', 't3.pdf', 't4.pdf', 't5.pdf', 't6.pdf']
    results = []
    for pdf in pdfs:
        res = await test_pdf(pdf)
        results.append(res)
        time.sleep(1) # 부하 방지
    
    with open('test_results_summary.json', 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\n✅ 모든 테스트 완료")

if __name__ == "__main__":
    asyncio.run(main())

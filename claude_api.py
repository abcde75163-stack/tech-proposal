import anthropic
import streamlit as st
import os
from pathlib import Path
 
# 루트 평탄 구조: prompts/ 폴더가 app.py와 같은 레벨에 있음
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
 
 
def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8")
 
 
def run_gap_analysis(api_key, patent_text, company_name, ir_text) -> str:
    system_prompt = load_prompt("gap_analysis.txt")
    ir_section = ir_text.strip() if ir_text.strip() else "없음. 공개 정보 기반으로 추론해주세요."
    user_message = f"""특허 명세서:\n{patent_text}\n\n수요기업명: {company_name}\n\n수요기업 IR/정보:\n{ir_section}\n\n위 정보를 바탕으로 갭 진단 초안을 작성해주세요.\n다음 세 가지를 순서대로 포함하세요:\n1. 수요기업의 현재 강점 (1~2문장)\n2. 확인되는 기술 공백 (2~3문장, 구체적으로)\n3. 본 기술이 이 공백을 어떻게 메우는지 (1~2문장)"""
    client = anthropic.Anthropic(api_key=api_key)
    with st.spinner("갭 진단 분석 중..."):
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1000,
            system=system_prompt, messages=[{"role": "user", "content": user_message}])
    return response.content[0].text
 
 
def stream_proposal(api_key, proposal_type, patent_text, company_name, ir_text, approved_gap,
                     max_continuations=3):
    """
    제안서를 스트리밍으로 생성한다.
 
    정식형(8~10페이지, 5개 섹션 + 참고문헌)은 한 번의 호출로 끝까지 생성되지
    않을 수 있으므로, stop_reason이 "max_tokens"로 잘린 경우 이전 내용을
    assistant 턴으로 그대로 되돌려주고 "이어서 작성"을 요청하는 방식으로
    최대 max_continuations회까지 자동으로 이어쓴다.
    """
    prompt_file = "teaser.txt" if proposal_type == "티저형" else "formal.txt"
    system_prompt = load_prompt(prompt_file)
    ir_section = ir_text.strip() if ir_text.strip() else "없음 (공개 정보 기반 추론 적용)"
    type_kr = "티저형 제안서" if proposal_type == "티저형" else "정식 제안보고서"
    gap_section = "SECTION 2의 핵심 진단" if proposal_type == "티저형" else "03섹션 핵심 진단 및 갭 분석표"
    user_message = f"""특허 명세서:\n{patent_text}\n\n수요기업명: {company_name}\n\n수요기업 IR/정보:\n{ir_section}\n\n[확정된 갭 진단 — 사용자 승인 완료]:\n{approved_gap}\n\n위 정보를 바탕으로 {type_kr}를 작성해주세요.\n갭 진단 내용을 {gap_section}에 반영하세요."""
 
    client = anthropic.Anthropic(api_key=api_key)
    # 정식형은 5개 섹션 + 표 다수 + 참고문헌까지 포함해야 하므로 넉넉히 설정.
    # 그래도 잘리면 아래 continuation 루프가 이어서 채운다.
    max_tokens = 4000 if proposal_type == "티저형" else 8000
    continuation_max_tokens = 4000
 
    messages = [{"role": "user", "content": user_message}]
    accumulated = ""
    continuations_used = 0
 
    while True:
        current_max_tokens = max_tokens if continuations_used == 0 else continuation_max_tokens
        with client.messages.stream(model="claude-sonnet-4-6", max_tokens=current_max_tokens,
                system=system_prompt, messages=messages) as stream:
            for text in stream.text_stream:
                accumulated += text
                yield text
            final_message = stream.get_final_message()
            stop_reason = final_message.stop_reason
 
        if stop_reason != "max_tokens" or continuations_used >= max_continuations:
            break
 
        continuations_used += 1
        messages = messages + [
            {"role": "assistant", "content": accumulated},
            {"role": "user", "content": (
                "출력이 중간에 잘렸습니다. 처음부터 다시 쓰지 말고, "
                "직전에 중단된 지점 바로 다음부터 자연스럽게 이어서 작성해주세요. "
                "남은 섹션(참고문헌 포함)까지 끝까지 작성해야 합니다."
            )},
        ]

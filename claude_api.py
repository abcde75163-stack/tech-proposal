import anthropic
import streamlit as st
import os
from pathlib import Path

PROMPTS_DIR = Path(os.path.abspath(__file__)).parent.parent / "prompts"


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def run_gap_analysis(
    api_key: str,
    patent_text: str,
    company_name: str,
    ir_text: str,
) -> str:
    """Step 2: 갭 진단 초안 생성"""
    system_prompt = load_prompt("gap_analysis.txt")

    ir_section = ir_text.strip() if ir_text.strip() else "없음. 공개 정보 기반으로 추론해주세요."

    user_message = f"""특허 명세서:
{patent_text}

수요기업명: {company_name}

수요기업 IR/정보:
{ir_section}

위 정보를 바탕으로 갭 진단 초안을 작성해주세요.
다음 세 가지를 순서대로 포함하세요:
1. 수요기업의 현재 강점 (1~2문장)
2. 확인되는 기술 공백 (2~3문장, 구체적으로)
3. 본 기술이 이 공백을 어떻게 메우는지 (1~2문장)"""

    client = anthropic.Anthropic(api_key=api_key)

    with st.spinner("갭 진단 분석 중..."):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
    return response.content[0].text


def stream_proposal(
    api_key: str,
    proposal_type: str,
    patent_text: str,
    company_name: str,
    ir_text: str,
    approved_gap: str,
):
    """Step 3: 제안서 스트리밍 생성. 제너레이터로 텍스트 청크를 yield"""
    prompt_file = "teaser.txt" if proposal_type == "티저형" else "formal.txt"
    system_prompt = load_prompt(prompt_file)

    ir_section = ir_text.strip() if ir_text.strip() else "없음 (공개 정보 기반 추론 적용)"

    user_message = f"""특허 명세서:
{patent_text}

수요기업명: {company_name}

수요기업 IR/정보:
{ir_section}

[확정된 갭 진단 — 사용자 승인 완료]:
{approved_gap}

위 정보를 바탕으로 {'티저형 제안서' if proposal_type == '티저형' else '정식 제안보고서'}를 작성해주세요.
갭 진단 내용을 {'SECTION 2의 핵심 진단' if proposal_type == '티저형' else '03섹션 핵심 진단 및 갭 분석표'}에 반영하세요."""

    client = anthropic.Anthropic(api_key=api_key)
    max_tokens = 3000 if proposal_type == "티저형" else 6000

    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            yield text

from pathlib import Path
import time

from openai import APIConnectionError, APIError, APITimeoutError, BadRequestError, OpenAI, RateLimitError
import streamlit as st


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DEFAULT_MODEL = "gpt-5"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5


def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    return path.read_text(encoding="utf-8")


def _get_model() -> str:
    return st.secrets.get("OPENAI_MODEL", DEFAULT_MODEL)


def _web_search_tools(ir_text: str) -> list[dict]:
    if ir_text.strip():
        return []
    return [{"type": "web_search_preview"}]


def _is_transient_error(error: Exception) -> bool:
    return isinstance(error, (APIConnectionError, APIError, APITimeoutError, RateLimitError))


def _is_web_search_unsupported(error: BadRequestError) -> bool:
    message = str(error).lower()
    return "web_search" in message or "tool" in message


def _extract_output_text(response) -> str:
    """Responses API 응답에서 텍스트를 최대한 안정적으로 추출."""
    output_text = getattr(response, "output_text", "")
    if output_text:
        return output_text.strip()

    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)

    return "\n".join(chunks).strip()


def _incomplete_reason(response) -> str:
    incomplete_details = getattr(response, "incomplete_details", None)
    return getattr(incomplete_details, "reason", "") if incomplete_details else ""


def _create_with_retries(client: OpenAI, create_kwargs: dict):
    use_tools = bool(create_kwargs.get("tools"))

    for attempt in range(MAX_RETRIES):
        try:
            return client.responses.create(**create_kwargs)
        except BadRequestError as error:
            if use_tools and _is_web_search_unsupported(error):
                create_kwargs = dict(create_kwargs)
                create_kwargs.pop("tools", None)
                use_tools = False
                st.warning("웹 검색 도구를 사용할 수 없어, 업로드된 자료와 입력값만으로 다시 시도합니다.")
                continue
            raise
        except Exception as error:
            if not _is_transient_error(error) or attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_BASE_DELAY * (2**attempt))


def run_fit_analysis(api_key, patent_text, company_name, ir_text) -> str:
    system_prompt = load_prompt("fit_analysis.txt")
    ir_section = ir_text.strip() if ir_text.strip() else "없음. 공개 정보 기반으로 추론해주세요."
    user_message = f"""특허 명세서:\n{patent_text}\n\n수요기업명: {company_name}\n\n수요기업 자료/정보:\n{ir_section}\n\n위 정보를 바탕으로 기업 적합성 및 제안 방향 초안을 작성해주세요.\n특히 다음을 포함하세요:\n1. 수요기업의 현재 사업/역량 요약\n2. 본 기술과 연결 가능한 접점\n3. 현실적인 적용 가능 범위\n4. 제안 적합도 판단\n5. 선결 검토사항 또는 리스크\n6. 티저형/제안형 중 어떤 접근이 적절한지와 1차 제안 방향"""

    client = OpenAI(api_key=api_key)
    create_kwargs = {
        "model": _get_model(),
        "instructions": system_prompt,
        "input": [{"role": "user", "content": user_message}],
        "max_output_tokens": 3000,
    }
    tools = _web_search_tools(ir_text)
    if tools:
        create_kwargs["tools"] = tools

    with st.spinner("기업 적합성 및 제안 방향 분석 중..."):
        response = _create_with_retries(client, create_kwargs)
    output_text = _extract_output_text(response)
    if not output_text:
        reason = _incomplete_reason(response)
        if reason == "max_output_tokens":
            raise RuntimeError("AI 응답이 출력 토큰 한도에 걸렸습니다. OPENAI_MODEL을 gpt-5-mini로 바꾸거나 잠시 후 다시 시도해주세요.")
        raise RuntimeError("AI 응답이 비어 있습니다. 모델 설정 또는 입력 자료 길이를 확인한 뒤 다시 시도해주세요.")
    return output_text


def generate_proposal_chunks(
    api_key,
    proposal_type,
    patent_text,
    company_name,
    ir_text,
    approved_fit,
    max_continuations=3,
):
    """
    제안서를 생성한 뒤 작은 조각으로 나누어 반환한다.

    안정성을 위해 일반 생성 응답을 받아 UI에 chunk 형태로 전달한다.
    제안형(8~10페이지, 7개 섹션 + 참고문헌)은 한 번의 호출로 끝까지 생성되지
    않을 수 있으므로, max_output_tokens로 잘린 경우 이전 응답을 이어받아
    최대 max_continuations회까지 자동으로 이어쓴다.
    """
    prompt_file = "teaser.txt" if proposal_type == "티저형" else "proposal.txt"
    system_prompt = load_prompt(prompt_file)
    ir_section = ir_text.strip() if ir_text.strip() else "없음 (공개 정보 기반 추론 적용)"
    type_kr = "티저형 제안서" if proposal_type == "티저형" else "제안형 기술이전 제안서"
    fit_section = "SECTION 3의 핵심 진단" if proposal_type == "티저형" else "03섹션 귀사 현황 및 기술 적합성 분석"
    user_message = f"""특허 명세서:\n{patent_text}\n\n수요기업명: {company_name}\n\n수요기업 자료/정보:\n{ir_section}\n\n[확정된 기업 적합성 및 제안 방향 - 사용자 승인 완료]:\n{approved_fit}\n\n위 정보를 바탕으로 {type_kr}를 작성해주세요.\n승인된 적합성 분석과 제안 방향을 {fit_section}에 반영하세요."""

    client = OpenAI(api_key=api_key)
    max_tokens = 4000 if proposal_type == "티저형" else 8000
    continuation_max_tokens = 4000
    tools = _web_search_tools(ir_text)

    input_messages = [{"role": "user", "content": user_message}]
    previous_response_id = None
    continuations_used = 0

    while True:
        current_max_tokens = max_tokens if continuations_used == 0 else continuation_max_tokens
        create_kwargs = {
            "model": _get_model(),
            "instructions": system_prompt,
            "input": input_messages,
            "max_output_tokens": current_max_tokens,
        }
        if previous_response_id:
            create_kwargs["previous_response_id"] = previous_response_id
        if tools:
            create_kwargs["tools"] = tools

        final_response = _create_with_retries(client, create_kwargs)
        output_text = _extract_output_text(final_response)
        if not output_text:
            raise RuntimeError("AI 응답이 비어 있습니다. 잠시 후 다시 시도해주세요.")

        for start in range(0, len(output_text), 500):
            yield output_text[start:start + 500]

        previous_response_id = final_response.id
        reason = _incomplete_reason(final_response)

        if reason != "max_output_tokens" or continuations_used >= max_continuations:
            break

        continuations_used += 1
        input_messages = [
            {
                "role": "user",
                "content": (
                    "출력이 중간에 잘렸습니다. 처음부터 다시 쓰지 말고, "
                    "직전에 중단된 지점 바로 다음부터 자연스럽게 이어서 작성해주세요. "
                    "남은 섹션(참고문헌 포함)까지 끝까지 작성해야 합니다."
                ),
            }
        ]

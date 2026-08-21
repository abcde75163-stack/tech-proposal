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


def run_gap_analysis(api_key, patent_text, company_name, ir_text) -> str:
    system_prompt = load_prompt("gap_analysis.txt")
    ir_section = ir_text.strip() if ir_text.strip() else "없음. 공개 정보 기반으로 추론해주세요."
    user_message = f"""특허 명세서:\n{patent_text}\n\n수요기업명: {company_name}\n\n수요기업 IR/정보:\n{ir_section}\n\n위 정보를 바탕으로 갭 진단 초안을 작성해주세요.\n다음 세 가지를 순서대로 포함하세요:\n1. 수요기업의 현재 강점 (1~2문장)\n2. 확인되는 기술 공백 (2~3문장, 구체적으로)\n3. 본 기술이 이 공백을 어떻게 메우는지 (1~2문장)"""

    client = OpenAI(api_key=api_key)
    create_kwargs = {
        "model": _get_model(),
        "instructions": system_prompt,
        "input": [{"role": "user", "content": user_message}],
        "max_output_tokens": 1000,
    }
    tools = _web_search_tools(ir_text)
    if tools:
        create_kwargs["tools"] = tools

    with st.spinner("갭 진단 분석 중..."):
        response = _create_with_retries(client, create_kwargs)
    if not response.output_text.strip():
        raise RuntimeError("AI 응답이 비어 있습니다. 잠시 후 다시 시도해주세요.")
    return response.output_text


def stream_proposal(
    api_key,
    proposal_type,
    patent_text,
    company_name,
    ir_text,
    approved_gap,
    max_continuations=3,
):
    """
    제안서를 스트리밍으로 생성한다.

    정식형(8~10페이지, 5개 섹션 + 참고문헌)은 한 번의 호출로 끝까지 생성되지
    않을 수 있으므로, max_output_tokens로 잘린 경우 이전 응답을 이어받아
    최대 max_continuations회까지 자동으로 이어쓴다.
    """
    prompt_file = "teaser.txt" if proposal_type == "티저형" else "formal.txt"
    system_prompt = load_prompt(prompt_file)
    ir_section = ir_text.strip() if ir_text.strip() else "없음 (공개 정보 기반 추론 적용)"
    type_kr = "티저형 제안서" if proposal_type == "티저형" else "정식 제안보고서"
    gap_section = "SECTION 2의 핵심 진단" if proposal_type == "티저형" else "03섹션 핵심 진단 및 갭 분석표"
    user_message = f"""특허 명세서:\n{patent_text}\n\n수요기업명: {company_name}\n\n수요기업 IR/정보:\n{ir_section}\n\n[확정된 갭 진단 - 사용자 승인 완료]:\n{approved_gap}\n\n위 정보를 바탕으로 {type_kr}를 작성해주세요.\n갭 진단 내용을 {gap_section}에 반영하세요."""

    client = OpenAI(api_key=api_key)
    max_tokens = 4000 if proposal_type == "티저형" else 8000
    continuation_max_tokens = 4000
    tools = _web_search_tools(ir_text)

    input_messages = [{"role": "user", "content": user_message}]
    previous_response_id = None
    continuations_used = 0

    while True:
        current_max_tokens = max_tokens if continuations_used == 0 else continuation_max_tokens
        stream_kwargs = {
            "model": _get_model(),
            "instructions": system_prompt,
            "input": input_messages,
            "max_output_tokens": current_max_tokens,
        }
        if previous_response_id:
            stream_kwargs["previous_response_id"] = previous_response_id
        if tools:
            stream_kwargs["tools"] = tools

        yielded_this_response = False
        for attempt in range(MAX_RETRIES):
            yielded_this_attempt = False
            try:
                with client.responses.stream(**stream_kwargs) as stream:
                    for event in stream:
                        if event.type == "response.output_text.delta":
                            yielded_this_attempt = True
                            yielded_this_response = True
                            yield event.delta

                    final_response = stream.get_final_response()
                break
            except BadRequestError as error:
                if tools and "tools" in stream_kwargs and _is_web_search_unsupported(error):
                    stream_kwargs = dict(stream_kwargs)
                    stream_kwargs.pop("tools", None)
                    tools = []
                    st.warning("웹 검색 도구를 사용할 수 없어, 업로드된 자료와 입력값만으로 다시 시도합니다.")
                    continue
                raise
            except Exception as error:
                if yielded_this_attempt or not _is_transient_error(error) or attempt == MAX_RETRIES - 1:
                    raise
                time.sleep(RETRY_BASE_DELAY * (2**attempt))
        else:
            raise RuntimeError("AI 응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요.")

        if not yielded_this_response:
            raise RuntimeError("AI 응답이 비어 있습니다. 잠시 후 다시 시도해주세요.")

        previous_response_id = final_response.id
        incomplete_details = getattr(final_response, "incomplete_details", None)
        reason = getattr(incomplete_details, "reason", None)

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

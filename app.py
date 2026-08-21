import streamlit as st
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from file_parser import parse_uploaded_file
from openai_api import run_fit_analysis, generate_proposal_chunks
from docx_generator import markdown_to_docx

# ── 페이지 설정
st.set_page_config(
    page_title="수요기업 맞춤형 기술이전 제안서 시스템",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main-title { font-size:1.55rem; font-weight:700; color:#1F497D; margin-bottom:0.15rem; }
    .sub-title { font-size:0.9rem; color:#666; margin-bottom:1.1rem; }
    .step-badge { display:inline-block; background:#2E75B6; color:white; border-radius:50%;
        width:24px; height:24px; text-align:center; line-height:24px;
        font-weight:bold; font-size:0.85rem; margin-right:8px; }
    .step-header { font-size:1.02rem; font-weight:600; color:#1F497D; margin:1.2rem 0 0.55rem 0; }
    .warning-box { background:#FFF8E1; border-left:4px solid #FFA000;
        padding:0.65rem 0.85rem; border-radius:4px; font-size:0.86rem; margin:0.4rem 0; }
    .small-note { color:#666; font-size:0.82rem; margin-top:0.25rem; }
</style>
""", unsafe_allow_html=True)

# ── API Key: Streamlit Secrets에서 로드 (Manage app > Secrets 에 기입)
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except (KeyError, FileNotFoundError):
    api_key = ""

# API Key가 없으면 앱 전체를 차단
if not api_key:
    st.error("⚠️ API Key가 설정되지 않았습니다. Streamlit Cloud의 **Manage app > Secrets**에 아래 형식으로 입력해주세요.")
    st.code('OPENAI_API_KEY = "sk-..."\nOPENAI_MODEL = "gpt-5"', language="toml")
    st.stop()

# ── 사이드바
with st.sidebar:
    st.markdown("### 설정")
    company_name = st.text_input("수요기업명", placeholder="예: ㈜센디")
    proposal_type = st.radio("제안서 유형", ["티저형 (2~3페이지)", "제안형 (6~8페이지)"],
        help="티저형: 미팅 전 첫 컨택용 / 제안형: 미팅 후 적용 가능성 심층 검토용")
    proposal_type_key = "티저형" if "티저형" in proposal_type else "제안형"

# ── 메인
st.markdown('<div class="main-title">수요기업 맞춤형 기술이전 제안서</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">특허와 수요기업 정보를 바탕으로 제안 방향을 정리하고 Word 제안서를 생성합니다.</div>', unsafe_allow_html=True)

for key in ["patent_text", "ir_text", "fit_draft", "proposal_md", "step"]:
    if key not in st.session_state:
        st.session_state[key] = "" if key != "step" else 1

# STEP 1
st.markdown('<div class="step-header"><span class="step-badge">1</span>자료 업로드</div>', unsafe_allow_html=True)
col1, col2 = st.columns(2)

with col1:
    patent_file = st.file_uploader("특허 명세서 *필수", type=["docx","pdf"], key="patent_upload")
    if patent_file:
        text = parse_uploaded_file(patent_file)
        if text:
            st.session_state.patent_text = text
            st.success(f"파싱 완료 · {len(text):,}자")

with col2:
    ir_file = st.file_uploader("수요기업 자료 (선택)", type=["docx","pdf"], key="ir_upload")
    if ir_file:
        text = parse_uploaded_file(ir_file)
        if text:
            st.session_state.ir_text = text
            st.success(f"파싱 완료 · {len(text):,}자")
    else:
        st.markdown('<div class="small-note">기업자료가 없으면 공개자료 기반으로 작성합니다.</div>', unsafe_allow_html=True)

# STEP 2
st.markdown('<div class="step-header"><span class="step-badge">2</span>기업 적합성 및 제안 방향 확인</div>', unsafe_allow_html=True)

can_analyze = bool(st.session_state.patent_text and company_name)
if not can_analyze:
    missing = []
    if not st.session_state.patent_text: missing.append("특허 명세서")
    if not company_name: missing.append("수요기업명 (사이드바)")
    st.markdown(f'<div class="warning-box">필요 항목: {", ".join(missing)}</div>', unsafe_allow_html=True)

analyze_btn = st.button("적합성 분석 생성", disabled=not can_analyze, use_container_width=False)

if analyze_btn and can_analyze:
    try:
        draft = run_fit_analysis(api_key=api_key, patent_text=st.session_state.patent_text,
                                  company_name=company_name, ir_text=st.session_state.ir_text)
        st.session_state.fit_draft = draft
        st.session_state.step = 2
    except Exception as e:
        st.error(f"적합성 분석 생성 중 오류: {e}")

if st.session_state.fit_draft:
    with st.expander("분석 결과 보기/수정", expanded=True):
        edited_fit = st.text_area(label="적합성 분석 편집", value=st.session_state.fit_draft,
                                  height=180, label_visibility="collapsed")
        st.session_state.fit_draft = edited_fit

    if st.button("이 방향으로 제안서 작성", type="primary", use_container_width=False):
        st.session_state.step = 3
        st.rerun()

# STEP 3
st.markdown('<div class="step-header"><span class="step-badge">3</span>제안서 생성</div>', unsafe_allow_html=True)

can_generate = st.session_state.step >= 3 and bool(st.session_state.fit_draft)
if not can_generate:
    st.caption("적합성 분석을 승인하면 생성 버튼이 활성화됩니다.")
else:
    st.caption(f"{company_name} · {proposal_type_key}")

    generate_btn = st.button("제안서 생성", type="primary", use_container_width=False)

    if generate_btn:
        st.session_state.proposal_md = ""
        full_text = ""

        # 진행 상황 표시 (세부 내용 대신 단계별 메시지만)
        progress_bar = st.progress(0)
        status_msg = st.empty()

        steps = [
            (10, "자료 분석 중..."),
            (35, "제안 방향 반영 중..."),
            (70, "제안서 작성 중..."),
            (90, "문서 정리 중..."),
        ]
        step_idx = 0
        char_thresholds = [200, 900, 1800, 3000]

        try:
            for chunk in generate_proposal_chunks(api_key=api_key, proposal_type=proposal_type_key,
                patent_text=st.session_state.patent_text, company_name=company_name,
                ir_text=st.session_state.ir_text, approved_fit=st.session_state.fit_draft):
                full_text += chunk

                # 글자 수 기준으로 진행 단계 업데이트
                if step_idx < len(steps) and len(full_text) >= char_thresholds[step_idx]:
                    progress_bar.progress(steps[step_idx][0])
                    status_msg.markdown(f"**{steps[step_idx][1]}**")
                    step_idx += 1

            progress_bar.progress(100)
            status_msg.markdown("**제안서 생성 완료**")
            st.session_state.proposal_md = full_text

        except Exception as e:
            progress_bar.empty()
            status_msg.empty()
            st.error(f"제안서 생성 중 오류: {e}")

    if st.session_state.proposal_md:
        st.divider()
        st.markdown("#### 다운로드")
        try:
            docx_bytes = markdown_to_docx(st.session_state.proposal_md)
            st.download_button(
                label="Word (.docx) 다운로드",
                data=docx_bytes,
                file_name=f"기술이전제안서_{company_name}_{proposal_type_key}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=False,
            )
        except Exception as e:
            st.error(f"DOCX 변환 오류: {e}")

        if st.button("처음부터 다시 시작"):
            for key in ["patent_text","ir_text","fit_draft","proposal_md"]:
                st.session_state[key] = ""
            st.session_state.step = 1
            st.rerun()

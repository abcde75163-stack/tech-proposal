import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from modules.file_parser import parse_uploaded_file
from modules.claude_api import run_gap_analysis, stream_proposal
from modules.docx_generator import markdown_to_docx

# ── 페이지 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="기술이전 제안서 시스템",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-title {
        font-size: 1.6rem; font-weight: 700;
        color: #1F497D; margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.9rem; color: #666; margin-bottom: 1.5rem;
    }
    .step-badge {
        display: inline-block;
        background: #2E75B6; color: white;
        border-radius: 50%; width: 28px; height: 28px;
        text-align: center; line-height: 28px;
        font-weight: bold; font-size: 0.85rem;
        margin-right: 8px;
    }
    .step-header {
        font-size: 1.05rem; font-weight: 600;
        color: #1F497D; margin: 1rem 0 0.5rem 0;
    }
    .info-box {
        background: #EEF4FB; border-left: 4px solid #2E75B6;
        padding: 0.8rem 1rem; border-radius: 4px;
        font-size: 0.88rem; margin: 0.5rem 0;
    }
    .warning-box {
        background: #FFF8E1; border-left: 4px solid #FFA000;
        padding: 0.8rem 1rem; border-radius: 4px;
        font-size: 0.88rem; margin: 0.5rem 0;
    }
    div[data-testid="stTextArea"] textarea {
        font-size: 0.88rem;
    }
</style>
""", unsafe_allow_html=True)

# ── 사이드바 ──────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ 설정")
    st.divider()

    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        help="입력된 키는 이 세션에서만 사용되며 서버에 저장되지 않습니다.",
    )
    if api_key:
        st.success("API Key 입력 완료", icon="✅")
    else:
        st.markdown(
            '<div class="warning-box">API Key를 입력해야 제안서 생성이 가능합니다.</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    proposal_type = st.radio(
        "제안서 유형",
        ["티저형 (2~3페이지)", "정식형 (8~10페이지)"],
        help="티저형: 첫 컨택용 / 정식형: 미팅 후 심층 검토용",
    )
    proposal_type_key = "티저형" if "티저형" in proposal_type else "정식형"

    st.divider()
    company_name = st.text_input("수요기업명", placeholder="예: ㈜센디")

    st.divider()
    st.markdown("##### 📌 단계별 안내")
    st.markdown("""
1. **자료 업로드** — 특허 명세서 + IR
2. **갭 진단 확인** — 초안 수정 후 승인
3. **제안서 생성** — 다운로드
    """)
    st.divider()
    st.caption("© 산학협력단 기술이전팀\nPowered by Claude AI")

# ── 메인 영역 ─────────────────────────────────────────────────
st.markdown('<div class="main-title">📄 기술이전 제안서 시스템</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">특허 명세서와 수요기업 정보를 업로드하면 AI가 맞춤형 제안서를 자동 생성합니다.</div>',
    unsafe_allow_html=True,
)

# 세션 상태 초기화
for key in ["patent_text", "ir_text", "gap_draft", "proposal_md", "step"]:
    if key not in st.session_state:
        st.session_state[key] = "" if key != "step" else 1

# ── STEP 1: 자료 업로드 ───────────────────────────────────────
st.markdown('<div class="step-header"><span class="step-badge">1</span>자료 업로드</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    patent_file = st.file_uploader(
        "특허 명세서 *필수",
        type=["docx", "pdf"],
        key="patent_upload",
        help="DOCX 또는 PDF 형식",
    )
    if patent_file:
        text = parse_uploaded_file(patent_file)
        if text:
            st.session_state.patent_text = text
            st.success(f"✅ 파싱 완료 — {len(text):,}자 추출")
            with st.expander("추출된 텍스트 미리보기"):
                st.text(text[:800] + "..." if len(text) > 800 else text)

with col2:
    ir_file = st.file_uploader(
        "수요기업 IR 자료 (선택)",
        type=["docx", "pdf"],
        key="ir_upload",
        help="없으면 Claude가 공개 정보 기반으로 추론합니다.",
    )
    if ir_file:
        text = parse_uploaded_file(ir_file)
        if text:
            st.session_state.ir_text = text
            st.success(f"✅ 파싱 완료 — {len(text):,}자 추출")
    else:
        st.markdown(
            '<div class="info-box">IR 자료가 없으면 Claude가 공개 정보를 기반으로 추론합니다. "(추정)" 표기가 적용됩니다.</div>',
            unsafe_allow_html=True,
        )

st.divider()

# ── STEP 2: 갭 진단 확인 ─────────────────────────────────────
st.markdown('<div class="step-header"><span class="step-badge">2</span>기업 분석 및 갭 진단 확인</div>', unsafe_allow_html=True)

can_analyze = bool(api_key and st.session_state.patent_text and company_name)

if not can_analyze:
    missing = []
    if not api_key:
        missing.append("API Key")
    if not st.session_state.patent_text:
        missing.append("특허 명세서")
    if not company_name:
        missing.append("수요기업명")
    st.markdown(
        f'<div class="warning-box">다음 항목을 먼저 입력해주세요: {", ".join(missing)}</div>',
        unsafe_allow_html=True,
    )

col_btn1, col_btn2 = st.columns([1, 5])
with col_btn1:
    analyze_btn = st.button(
        "🔍 갭 진단 생성",
        disabled=not can_analyze,
        use_container_width=True,
    )

if analyze_btn and can_analyze:
    try:
        draft = run_gap_analysis(
            api_key=api_key,
            patent_text=st.session_state.patent_text,
            company_name=company_name,
            ir_text=st.session_state.ir_text,
        )
        st.session_state.gap_draft = draft
        st.session_state.step = 2
    except Exception as e:
        st.error(f"갭 진단 생성 중 오류가 발생했습니다: {e}")

if st.session_state.gap_draft:
    st.markdown("**📝 갭 진단 초안** — 내용을 직접 수정한 후 승인하세요.")
    edited_gap = st.text_area(
        label="갭 진단 편집",
        value=st.session_state.gap_draft,
        height=200,
        label_visibility="collapsed",
    )
    st.session_state.gap_draft = edited_gap

    col_a, col_b = st.columns([1, 5])
    with col_a:
        approved = st.button("✅ 이 방향으로 제안서 작성", type="primary", use_container_width=True)
    if approved:
        st.session_state.step = 3
        st.rerun()

st.divider()

# ── STEP 3: 제안서 생성 ───────────────────────────────────────
st.markdown('<div class="step-header"><span class="step-badge">3</span>제안서 생성</div>', unsafe_allow_html=True)

can_generate = st.session_state.step >= 3 and bool(st.session_state.gap_draft)

if not can_generate:
    st.markdown(
        '<div class="info-box">Step 2에서 갭 진단을 승인하면 제안서 생성이 활성화됩니다.</div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div class="info-box">승인된 갭 진단을 기반으로 <b>{proposal_type_key} 제안서</b>를 생성합니다. — 수요기업: <b>{company_name}</b></div>',
        unsafe_allow_html=True,
    )

    col_g1, col_g2 = st.columns([1, 5])
    with col_g1:
        generate_btn = st.button("🚀 제안서 생성 시작", type="primary", use_container_width=True)

    if generate_btn:
        st.session_state.proposal_md = ""
        placeholder = st.empty()
        full_text = ""
        try:
            for chunk in stream_proposal(
                api_key=api_key,
                proposal_type=proposal_type_key,
                patent_text=st.session_state.patent_text,
                company_name=company_name,
                ir_text=st.session_state.ir_text,
                approved_gap=st.session_state.gap_draft,
            ):
                full_text += chunk
                placeholder.markdown(full_text)
            st.session_state.proposal_md = full_text
        except Exception as e:
            st.error(f"제안서 생성 중 오류가 발생했습니다: {e}")

    if st.session_state.proposal_md:
        st.divider()
        st.markdown("#### 📥 다운로드")
        col_d1, col_d2 = st.columns(2)

        with col_d1:
            # Markdown 다운로드
            st.download_button(
                label="📄 Markdown (.md) 다운로드",
                data=st.session_state.proposal_md.encode("utf-8"),
                file_name=f"기술이전제안서_{company_name}_{proposal_type_key}.md",
                mime="text/markdown",
                use_container_width=True,
            )

        with col_d2:
            # DOCX 다운로드
            try:
                docx_bytes = markdown_to_docx(st.session_state.proposal_md)
                st.download_button(
                    label="📝 Word (.docx) 다운로드",
                    data=docx_bytes,
                    file_name=f"기술이전제안서_{company_name}_{proposal_type_key}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"DOCX 변환 오류: {e}")
                st.info("Markdown 버전을 먼저 다운로드 받으세요.")

        st.divider()
        st.markdown("#### 🔄 새 제안서 작성")
        if st.button("처음부터 다시 시작"):
            for key in ["patent_text", "ir_text", "gap_draft", "proposal_md"]:
                st.session_state[key] = ""
            st.session_state.step = 1
            st.rerun()

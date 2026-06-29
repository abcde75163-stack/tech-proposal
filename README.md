# 기술이전 제안서 자동 생성 시스템

대학 산학협력단 기술이전팀을 위한 AI 기반 제안서 작성 도구입니다.

## 기능

- **티저형 제안서** (2~3페이지): 기업 첫 컨택용
- **정식형 제안서** (8~10페이지): 미팅 후 심층 검토용
- 특허 명세서 (DOCX/PDF) 자동 파싱
- 수요기업 갭 진단 → 사용자 확인 → 제안서 생성 (하이브리드 방식)
- Markdown / Word(.docx) 다운로드

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Cloud 배포

1. GitHub에 이 폴더를 레포지토리로 업로드
2. https://share.streamlit.io 접속
3. 레포지토리 연결 → `app.py` 선택 → Deploy
4. 각 사용자가 자신의 Anthropic API Key를 앱에 직접 입력하여 사용

## 파일 구조

```
tech_transfer_app/
├── app.py                  # 메인 앱
├── modules/
│   ├── file_parser.py      # DOCX/PDF 파싱
│   ├── claude_api.py       # Claude API 호출
│   └── docx_generator.py   # Markdown → DOCX 변환
├── prompts/
│   ├── gap_analysis.txt    # 갭 진단 프롬프트
│   ├── teaser.txt          # 티저형 프롬프트
│   └── formal.txt          # 정식형 프롬프트
├── requirements.txt
└── .streamlit/
    ├── config.toml         # 테마
    └── secrets.toml.example
```

## 향후 확장 계획

- [ ] 기관별 로그인 및 계정 관리
- [ ] Virtual Firm 분석 모듈 연결
- [ ] API 사용량 트래킹
- [ ] 구독 과금 모델

## 보안 주의사항

- 특허 명세서(미공개)를 외부 AI API로 전송합니다.
- 배포 전 기관 내부 보안 정책 검토를 권장합니다.
- API Key는 브라우저 세션에만 저장되며 서버에 기록되지 않습니다.

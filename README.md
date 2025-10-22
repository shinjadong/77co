# 법인카드 사용용도 AI 자동분류 프로그램

칠칠기업 법인카드 거래내역의 사용용도를 AI로 자동 분류하는 시스템

버전: 1.0
최종 업데이트: 2025-10-22

---

## 주요 기능

### 1. 지능형 4단계 분류 파이프라인
```
입력 파일 (XLSX/CSV)
   ↓
1️⃣ 정확 일치 룩업 (정답 DB 직접 매칭)
   ↓ 미매칭 시
2️⃣ Fuzzy/N-gram 유사 매칭 (편집거리 기반)
   ↓ 미매칭 시
3️⃣ Claude API 예측 (신규 가맹점 AI 분류)
   ↓
4️⃣ 규칙 기반 후처리 (키워드 검증)
   ↓
법인카드_(월)월_(카드번호).csv/xlsx
```

### 2. AI 최종 검토 시스템
- 낮은 신뢰도 거래 재검토
- 분류 적절성 평가
- 자동확정/AI수정/수동검토 결정

### 3. 피드백 루프
- 확정 라벨 자동 수집
- 정답 DB 업데이트
- 재학습 트리거 (50건 단위)

---

## 빠른 시작

### 설치
```bash
cd card_classifier
pip install -r requirements.txt

# .env 파일 생성 (.env.example 참고)
cp .env.example .env
# ANTHROPIC_API_KEY 입력
```

### 기본 사용법

#### 전체 프로세스 (권장)
```bash
# 1단계: 분류 실행
python3 main.py classify \
  --input "카드명세서.xlsx" \
  --output "output/분류결과.csv" \
  --claude \
  --feedback

# 2단계: 최종 검토 및 확정
python3 main.py finalize \
  --input "output/분류결과.csv" \
  --card "3987"

# → 자동 생성: 법인카드_(월)월_3987.csv/xlsx
```

#### 원스텝 실행
```bash
python3 main.py classify --input "카드.xlsx" --claude && \
python3 main.py finalize --input "output/분류결과_*.csv" --card "3987"
```

---

## 명령어 상세

### classify - 분류 실행
```bash
python3 main.py classify [옵션]

옵션:
  --input, -i PATH    입력 파일 (필수)
  --output, -o PATH   출력 파일 (선택, 기본: output/분류결과_시간.csv)
  --claude            Claude API 활성화 (미매칭 거래 자동 분류)
  --feedback          피드백 파일도 생성
  --card NUMBER       카드번호 (기본: 3987)

예시:
  python3 main.py classify -i 카드.xlsx --claude --feedback
  python3 main.py classify -i 9980.xlsx --claude --card 9980
```

### finalize - 최종 검토 및 확정
```bash
python3 main.py finalize [옵션]

옵션:
  --input, -i PATH    분류 결과 CSV (필수)
  --output, -o PATH   출력 파일 (선택, 자동 생성)
  --card NUMBER       카드번호 (기본: 3987)

예시:
  python3 main.py finalize -i output/분류결과.csv --card 9980
  # → 법인카드_(월)월_9980.csv/xlsx 자동 생성
```

### feedback - 피드백 수집
```bash
python3 main.py feedback [옵션]

옵션:
  --input, -i PATH    피드백 파일 (필수)

예시:
  python3 main.py feedback -i output/피드백_분류결과.csv
  # → 정답 DB 자동 업데이트 + 백업 생성
```

### test - 기능 테스트
```bash
python3 main.py test
# → 4개 테스트 케이스 실행
```

---

## 출력 파일 설명

### 1. 분류 결과 파일
```csv
승인일자,가맹점명_원본,가맹점명,이용금액,사용용도,신뢰도,라벨출처,근거
2025-07-31,와와식당,와와식당,0,중식대,0.95,Claude+규칙,"식당으로 판단..."
```

**컬럼**:
- `승인일자`: 거래 일자
- `가맹점명_원본`: 원본 가맹점명
- `가맹점명`: 정규화된 가맹점명
- `이용금액`: 거래 금액
- `사용용도`: 분류된 카테고리
- `신뢰도`: 0.0~1.0 (높을수록 확실)
- `라벨출처`: 정확일치/Fuzzy/Claude/Claude+규칙
- `근거`: AI 예측 근거 (Claude 사용 시)

### 2. 최종 확정 파일
```csv
승인일자,가맹점명,이용금액,사용용도,신뢰도,확정방법,검토의견
2025-07-31,와와식당,0,중식대,0.95,자동확정,
```

**컬럼**:
- `확정방법`: 자동확정/AI수정/수동검토필요
- `검토의견`: AI 검토자의 의견 (있는 경우)

### 3. 피드백 파일
```csv
승인일자,가맹점명_원본,이용금액,사용용도,신뢰도,라벨출처,확정용도
2025-07-19,주식회사 신사,0,기타,0.35,Claude,
```

**사용법**:
1. `확정용도` 컬럼에 올바른 사용용도 입력
2. `python3 main.py feedback --input 파일.csv` 실행
3. 정답 DB 자동 업데이트

---

## 처리 결과 요약

### 3987 카드 (7월 데이터)
```
총 거래: 42건
자동확정: 41건 (97.6%)
수동검토: 1건 (2.4%)
Claude 호출: 9건
비용: ~$0.07
```

### 9980 카드 (6월 데이터)
```
총 거래: 21건
자동확정: 12건 (57.1%)
AI수정: 6건 (28.6%)
수동검토: 3건 (14.3%)
Claude 호출: 19건
비용: ~$0.15
```

**총 처리**: 63건, 비용: ~$0.22 (약 300원)

---

## 프로젝트 구조

```
card_classifier/
├── main.py                    # 메인 실행 파일
├── config.py                  # 설정 관리
├── requirements.txt           # 의존성
├── .env.example               # 환경변수 템플릿
│
├── modules/
│   ├── preprocessor.py        # 전처리 (정규화)
│   ├── matchers.py            # 룩업/Fuzzy/N-gram
│   ├── claude_api.py          # Claude API 통합
│   ├── rules.py               # 규칙 엔진
│   ├── classifier.py          # 통합 분류기
│   ├── final_reviewer.py      # AI 최종 검토
│   └── feedback.py            # 피드백 및 DB 업데이트
│
├── data/
│   ├── master_db.csv          # 정답 DB (104→자동증가)
│   ├── master_db_backup_*.csv # 자동 백업
│   └── feedback_log.csv       # 피드백 이력
│
└── output/
    ├── 법인카드_(월)월_(카드).csv   # 최종 확정 파일
    ├── 법인카드_(월)월_(카드).xlsx
    └── 피드백_*.csv                # 검토용 파일
```

---

## 설정 파일 (.env)

```bash
# Claude API 설정
ANTHROPIC_API_KEY=your_api_key_here

# 모델 설정
CLAUDE_MODEL=claude-sonnet-4-5
MAX_TOKENS=1000
TEMPERATURE=0.2

# 매칭 임계값
FUZZY_THRESHOLD=0.85
NGRAM_SIZE=3
```

---

## 성능 지표

### 자동화율
- **정확 일치**: 65~97% (카드/월별 차이)
- **유사 매칭**: 추가 10~15%
- **AI 예측**: 나머지 모두 처리
- **최종 자동확정**: 60~98%

### 비용
- **미매칭 10%**: $0.50/월 (1,000건 기준)
- **미매칭 20%**: $1.00/월
- **건당**: ~2원

### 신뢰도
- **평균**: 0.73~0.97
- **정확일치**: 1.0
- **Fuzzy**: 0.85~0.95
- **Claude**: 0.35~1.0 (가맹점에 따라)

---

## 주의사항

### 1. API 키 보안
- `.env` 파일을 git에 커밋하지 마세요
- `.gitignore`에 `.env` 추가 권장

### 2. 데이터 품질
- 금액 0원 거래: 취소/오류 가능성
- 결측값(nan, NaT): 수동 확인 필요
- "수동검토필요" 항목은 반드시 검토

### 3. 정답 DB 관리
- 자동 백업이 `data/` 폴더에 생성됨
- 월 1회 백업 파일 정리 권장
- 50건 단위로 재학습 권장 메시지 출력

### 4. 새로운 카테고리
- AI가 제안하는 새 카테고리 (예: 접대비)는
- 경리 담당자가 검토 후 시스템 반영 여부 결정

---

## 문제 해결

### Q: "ANTHROPIC_API_KEY 오류"
```bash
# .env 파일 확인
cat .env

# API 키 설정 확인
echo $ANTHROPIC_API_KEY
```

### Q: "미매칭 건수가 많음"
- 정답 DB 확장 필요
- 피드백 기능으로 신규 가맹점 등록
- Fuzzy 임계값 조정 (config.py)

### Q: "신뢰도가 낮음"
- Few-shot 예시 개수 증가 (claude_api.py)
- 규칙 키워드 추가 (config.py)
- 정답 DB 품질 개선

### Q: "비용이 많이 나옴"
- `--claude` 플래그 없이 실행 (Phase 1만)
- 정답 DB 확장으로 API 호출 감소
- 배치 크기 조정

---

## 향후 개선 계획

### 단기 (완료)
- ✅ Claude API 통합
- ✅ 피드백 루프
- ✅ 동적 파일명 생성
- ✅ AI 최종 검토

### 중기 (3개월)
- [ ] 웹 UI (Streamlit/Flask)
- [ ] 대시보드 (통계 시각화)
- [ ] 이메일 알림
- [ ] 스케줄링 (월간 자동 실행)

### 장기 (6개월)
- [ ] 멀티 카드 통합 대시보드
- [ ] 예산 초과 알림
- [ ] 부가세 신고서 자동 생성
- [ ] 거래 패턴 이상 탐지

---

## 라이선스 및 저작권

© 2025 칠칠기업
내부 사용 전용

---

## 문의

기술 지원: 개발팀
프로젝트 문서: `/home/tlswk/77corp/claudedocs/AI_자동분류_프로그램_설계서.md`

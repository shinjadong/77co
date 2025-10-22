"""
설정 관리 모듈
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent

# 데이터 경로
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
MASTER_DB_PATH = DATA_DIR / "master_db.csv"

# Claude API 설정
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1000"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))

# 매칭 임계값
FUZZY_THRESHOLD = float(os.getenv("FUZZY_THRESHOLD", "0.85"))
NGRAM_SIZE = int(os.getenv("NGRAM_SIZE", "3"))

# 유의어 사전
SYNONYM_MAP = {
    "써브웨이": "서브웨이",
    "오일 뱅크": "오일뱅크",
    "GS 칼텍스": "GS칼텍스",
    "에스케이": "SK",
    "에스오일": "S-OIL",
}

# 정규화 패턴
NORMALIZE_PATTERNS = {
    # 괄호 제거 패턴
    "branch_pattern": r"\([^)]*점\)",  # (안산점), (고잔점) 등
    "generic_brackets": r"\([^)]*\)",  # 모든 괄호

    # 공백 정규화
    "multiple_spaces": r"\s+",

    # 특수문자 제거 (한글, 영문, 숫자, 일부 기호만 유지)
    "special_chars": r"[^\w\s가-힣a-zA-Z0-9\-]",
}

# 키워드 사전 (규칙 기반 보정용, Phase 3에서 활용)
KEYWORD_RULES = {
    "차량유지비(주유)": [
        "주유소", "GS칼텍스", "S-OIL", "오일뱅크", "SK에너지",
        "현대오일", "효창에너지", "셀프주유", "경유", "휘발유"
    ],
    "차량유지비(기타)": [
        "하이패스", "톨게이트", "IC주유소", "주차", "세차",
        "자동차정비", "자동차검사", "타이어", "통행"
    ],
    "중식대": [
        "맥도날드", "롯데리아", "버거킹", "써브웨이", "서브웨이",
        "스타벅스", "이디야", "커피", "카페", "식당", "반점",
        "중화요리", "순대국", "설렁탕", "본죽", "김밥"
    ],
    "사용료": [
        "한글과컴퓨터", "Microsoft", "Adobe", "오피스365",
        "AWS", "클라우드", "자동결제", "휴대폰", "메시지"
    ],
    "복리후생비(의료)": [
        "약국", "병원", "의원", "한의원", "치과", "의료"
    ],
    "소모품비": [
        "다이소", "문구", "토너", "잉크", "복사용지",
        "쿠팡", "이마트", "홈플러스", "비품"
    ],
}

# 디렉토리 생성
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

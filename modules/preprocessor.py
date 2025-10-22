"""
전처리 모듈

가맹점명 정규화 및 텍스트 전처리 기능 제공
"""
import re
import pandas as pd
from typing import Union, Optional
from pathlib import Path


class Preprocessor:
    """
    가맹점명 전처리 클래스

    주요 기능:
    - 파일 파싱 (XLSX, CSV)
    - 가맹점명 정규화
    - 유의어 통일
    """

    def __init__(self, synonym_map: dict = None):
        """
        Args:
            synonym_map: 유의어 사전 {원본: 표준}
        """
        self.synonym_map = synonym_map or {}

    def parse_file(self, file_path: Union[str, Path]) -> pd.DataFrame:
        """
        카드사 명세서 파일 파싱

        지원 형식: XLSX, XLS, CSV
        자동 컬럼 감지: 가맹점명, 승인일자, 이용금액

        Args:
            file_path: 파일 경로

        Returns:
            DataFrame with columns: 승인일자, 가맹점명, 이용금액
        """
        file_path = Path(file_path)

        # 파일 형식에 따라 읽기
        if file_path.suffix == ".csv":
            df = pd.read_csv(file_path, encoding="utf-8-sig")
        elif file_path.suffix in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"지원하지 않는 파일 형식: {file_path.suffix}")

        # 컬럼 매핑
        df = self._map_columns(df)

        return df

    def _map_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        컬럼명 자동 매핑

        카드사별 다른 컬럼명을 표준 컬럼명으로 변환
        """
        column_mapping = {
            # 가맹점명 변형
            "가맹점명": "가맹점명",
            "가맹점명/국가명": "가맹점명",
            "상호명": "가맹점명",
            "거래처": "가맹점명",

            # 결제일자 변형 (우선)
            "결제일자": "결제일자",
            "승인일자": "승인일자",
            "거래일자": "거래일자",
            "사용일자": "사용일자",
            "일자": "일자",

            # 이용금액 변형
            "이용금액": "이용금액",
            "거래금액": "이용금액",
            "사용금액": "이용금액",
            "청구금액": "이용금액",
        }

        # 현재 컬럼명 확인 및 매핑
        renamed_cols = {}
        for col in df.columns:
            if col in column_mapping:
                renamed_cols[col] = column_mapping[col]

        df = df.rename(columns=renamed_cols)

        # 일자 컬럼 통일 (결제일자 우선)
        date_col = None
        if "결제일자" in df.columns:
            date_col = "결제일자"
        elif "승인일자" in df.columns:
            date_col = "승인일자"
        elif "거래일자" in df.columns:
            date_col = "거래일자"
        elif "사용일자" in df.columns:
            date_col = "사용일자"
        elif "일자" in df.columns:
            date_col = "일자"

        if date_col and date_col != "결제일자":
            df["결제일자"] = df[date_col]
            # 원본 컬럼 제거 (중복 방지)
            if date_col in df.columns and date_col != "결제일자":
                df = df.drop(columns=[date_col])

        # 필수 컬럼 확인
        required_cols = ["가맹점명", "결제일자", "이용금액"]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            raise ValueError(f"필수 컬럼 누락: {missing_cols}")

        # 중복 컬럼 제거
        df = df.loc[:, ~df.columns.duplicated()]

        # 필요한 컬럼만 선택
        return df[required_cols]

    def normalize(self, merchant_name: str) -> str:
        """
        가맹점명 정규화

        처리 항목:
        1. 공백 정규화
        2. 괄호 내 지점명 제거
        3. 특수문자 제거
        4. 유의어 통일
        5. 대소문자 통일

        Args:
            merchant_name: 원본 가맹점명

        Returns:
            정규화된 가맹점명
        """
        if not merchant_name or pd.isna(merchant_name):
            return ""

        text = str(merchant_name).strip()

        # 1. 괄호 내 지점명 제거
        # 예: "맥도날드(안산점)" → "맥도날드"
        text = re.sub(r'\([^)]*점\)', '', text)

        # 2. 남은 괄호 내용 제거 (옵션)
        # 예: "(주)삼원기업" → "삼원기업"
        text = re.sub(r'\(주\)\s*', '', text)
        text = re.sub(r'\([^)]*\)', '', text)

        # 3. 공백 정규화
        text = re.sub(r'\s+', ' ', text).strip()

        # 4. 특수문자 제거 (한글, 영문, 숫자, 일부 기호만 유지)
        text = re.sub(r'[^\w\s가-힣a-zA-Z0-9\-]', '', text)

        # 5. 유의어 통일
        for original, standard in self.synonym_map.items():
            if original in text:
                text = text.replace(original, standard)

        # 6. 최종 공백 정리
        text = text.strip()

        return text

    def normalize_batch(self, merchants: pd.Series) -> pd.Series:
        """
        배치 정규화

        Args:
            merchants: 가맹점명 Series

        Returns:
            정규화된 가맹점명 Series
        """
        return merchants.apply(self.normalize)

    def clean_amount(self, amount: Union[str, int, float]) -> int:
        """
        금액 정규화

        "149,900" → 149900
        "149900원" → 149900

        Args:
            amount: 원본 금액

        Returns:
            정수형 금액
        """
        # None 또는 NaN 체크
        if amount is None or (isinstance(amount, float) and pd.isna(amount)):
            return 0

        # 이미 숫자형이면 그대로 반환
        if isinstance(amount, (int, float)):
            return int(amount)

        # 문자열 처리
        text = str(amount).strip()

        # 빈 문자열 체크
        if not text:
            return 0

        # 쉼표, 원 기호 제거
        text = text.replace(',', '').replace('원', '')

        try:
            return int(float(text))
        except (ValueError, TypeError):
            return 0

    def preprocess_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        DataFrame 전체 전처리

        Args:
            df: 원본 DataFrame

        Returns:
            전처리된 DataFrame
        """
        result = df.copy()

        # 가맹점명 정규화
        if "가맹점명" in result.columns:
            result["가맹점명_원본"] = result["가맹점명"]
            result["가맹점명"] = self.normalize_batch(result["가맹점명"])

        # 금액 정규화
        if "이용금액" in result.columns:
            # 중복 컬럼 제거
            if isinstance(result["이용금액"], pd.DataFrame):
                result["이용금액"] = result["이용금액"].iloc[:, 0]

            # 정규화 적용
            result["이용금액"] = result["이용금액"].apply(lambda x: self.clean_amount(x))

        # 일자 정규화 (결제일자 우선)
        if "결제일자" in result.columns:
            result["결제일자"] = pd.to_datetime(
                result["결제일자"],
                errors='coerce'
            )

        return result


# 편의 함수
def normalize_merchant(merchant_name: str, synonym_map: dict = None) -> str:
    """
    가맹점명 정규화 편의 함수

    Args:
        merchant_name: 원본 가맹점명
        synonym_map: 유의어 사전

    Returns:
        정규화된 가맹점명
    """
    preprocessor = Preprocessor(synonym_map=synonym_map)
    return preprocessor.normalize(merchant_name)

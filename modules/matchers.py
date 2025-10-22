"""
매칭 모듈

정확 일치, Fuzzy 매칭, N-gram 매칭 기능 제공
"""
import pandas as pd
from typing import Optional, Tuple
from rapidfuzz import fuzz, process


class ExactMatcher:
    """
    정확 일치 룩업 클래스

    정답 DB에서 완전 일치하는 가맹점명 검색
    """

    def __init__(self, master_db: pd.DataFrame):
        """
        Args:
            master_db: 정답 DB DataFrame
                       컬럼: 가맹점명, 사용용도
        """
        self.master_db = master_db
        # 빠른 검색을 위한 딕셔너리 생성
        self.lookup_dict = dict(
            zip(master_db["가맹점명"], master_db["사용용도"])
        )

    def match(self, merchant: str) -> Optional[str]:
        """
        정확 일치 검색

        Args:
            merchant: 정규화된 가맹점명

        Returns:
            사용용도 or None
        """
        return self.lookup_dict.get(merchant)

    def batch_match(self, merchants: pd.Series) -> pd.Series:
        """
        배치 정확 일치 검색

        Args:
            merchants: 가맹점명 Series

        Returns:
            사용용도 Series
        """
        return merchants.map(self.lookup_dict)


class FuzzyMatcher:
    """
    Fuzzy 매칭 클래스

    편집거리 기반 유사 매칭
    """

    def __init__(
        self,
        master_db: pd.DataFrame,
        threshold: float = 0.85
    ):
        """
        Args:
            master_db: 정답 DB DataFrame
            threshold: 유사도 임계값 (0.0~1.0)
        """
        self.master_db = master_db
        self.threshold = threshold
        self.merchants = master_db["가맹점명"].tolist()

    def match(
        self,
        merchant: str,
        scorer=fuzz.ratio
    ) -> Optional[Tuple[str, float]]:
        """
        Fuzzy 매칭 수행

        Args:
            merchant: 정규화된 가맹점명
            scorer: 유사도 계산 함수
                    - fuzz.ratio: 기본 편집거리
                    - fuzz.partial_ratio: 부분 매칭
                    - fuzz.token_sort_ratio: 토큰 순서 무시

        Returns:
            (사용용도, 유사도) or None
        """
        # 가장 유사한 가맹점명 찾기
        result = process.extractOne(
            merchant,
            self.merchants,
            scorer=scorer,
            score_cutoff=self.threshold * 100  # rapidfuzz는 0-100 스케일
        )

        if result is None:
            return None

        matched_merchant, score, _ = result

        # 해당 가맹점의 사용용도 찾기
        category = self.master_db[
            self.master_db["가맹점명"] == matched_merchant
        ]["사용용도"].iloc[0]

        return (category, score / 100.0)  # 0-1 스케일로 변환

    def batch_match(
        self,
        merchants: pd.Series,
        scorer=fuzz.ratio
    ) -> pd.DataFrame:
        """
        배치 Fuzzy 매칭

        Args:
            merchants: 가맹점명 Series
            scorer: 유사도 계산 함수

        Returns:
            DataFrame with columns: 사용용도, 유사도
        """
        results = []
        for merchant in merchants:
            match_result = self.match(merchant, scorer=scorer)
            if match_result:
                category, score = match_result
                results.append({"사용용도": category, "유사도": score})
            else:
                results.append({"사용용도": None, "유사도": 0.0})

        return pd.DataFrame(results)


class NGramMatcher:
    """
    N-gram 매칭 클래스

    부분 문자열 패턴 기반 매칭
    """

    def __init__(
        self,
        master_db: pd.DataFrame,
        n: int = 3,
        threshold: float = 0.6
    ):
        """
        Args:
            master_db: 정답 DB DataFrame
            n: N-gram 크기
            threshold: 유사도 임계값
        """
        self.master_db = master_db
        self.n = n
        self.threshold = threshold

    def _get_ngrams(self, text: str, n: int) -> set:
        """
        N-gram 추출

        Args:
            text: 입력 텍스트
            n: N-gram 크기

        Returns:
            N-gram 집합
        """
        if len(text) < n:
            return {text}
        return {text[i:i+n] for i in range(len(text) - n + 1)}

    def _ngram_similarity(self, text1: str, text2: str) -> float:
        """
        N-gram 기반 유사도 계산

        Jaccard 유사도 사용: |A ∩ B| / |A ∪ B|

        Args:
            text1, text2: 비교할 텍스트

        Returns:
            유사도 (0.0~1.0)
        """
        ngrams1 = self._get_ngrams(text1, self.n)
        ngrams2 = self._get_ngrams(text2, self.n)

        if not ngrams1 or not ngrams2:
            return 0.0

        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)

        return intersection / union if union > 0 else 0.0

    def match(self, merchant: str) -> Optional[Tuple[str, float]]:
        """
        N-gram 매칭 수행

        Args:
            merchant: 정규화된 가맹점명

        Returns:
            (사용용도, 유사도) or None
        """
        best_match = None
        best_score = 0.0

        for _, row in self.master_db.iterrows():
            db_merchant = row["가맹점명"]
            score = self._ngram_similarity(merchant, db_merchant)

            if score > best_score and score >= self.threshold:
                best_score = score
                best_match = row["사용용도"]

        if best_match:
            return (best_match, best_score)

        return None

    def batch_match(self, merchants: pd.Series) -> pd.DataFrame:
        """
        배치 N-gram 매칭

        Args:
            merchants: 가맹점명 Series

        Returns:
            DataFrame with columns: 사용용도, 유사도
        """
        results = []
        for merchant in merchants:
            match_result = self.match(merchant)
            if match_result:
                category, score = match_result
                results.append({"사용용도": category, "유사도": score})
            else:
                results.append({"사용용도": None, "유사도": 0.0})

        return pd.DataFrame(results)


class HybridMatcher:
    """
    하이브리드 매칭 클래스

    정확 일치 → Fuzzy → N-gram 순으로 시도
    """

    def __init__(
        self,
        master_db: pd.DataFrame,
        fuzzy_threshold: float = 0.85,
        ngram_threshold: float = 0.6,
        ngram_size: int = 3
    ):
        """
        Args:
            master_db: 정답 DB DataFrame
            fuzzy_threshold: Fuzzy 매칭 임계값
            ngram_threshold: N-gram 매칭 임계값
            ngram_size: N-gram 크기
        """
        self.exact_matcher = ExactMatcher(master_db)
        self.fuzzy_matcher = FuzzyMatcher(master_db, fuzzy_threshold)
        self.ngram_matcher = NGramMatcher(
            master_db,
            n=ngram_size,
            threshold=ngram_threshold
        )

    def match(self, merchant: str) -> dict:
        """
        하이브리드 매칭 수행

        Args:
            merchant: 정규화된 가맹점명

        Returns:
            {
                "사용용도": str or None,
                "신뢰도": float,
                "라벨출처": str  # "정확일치", "Fuzzy", "N-gram", "미매칭"
            }
        """
        # 1단계: 정확 일치
        exact_result = self.exact_matcher.match(merchant)
        if exact_result:
            return {
                "사용용도": exact_result,
                "신뢰도": 1.0,
                "라벨출처": "정확일치"
            }

        # 2단계: Fuzzy 매칭
        fuzzy_result = self.fuzzy_matcher.match(merchant)
        if fuzzy_result:
            category, score = fuzzy_result
            return {
                "사용용도": category,
                "신뢰도": score,
                "라벨출처": "Fuzzy"
            }

        # 3단계: N-gram 매칭
        ngram_result = self.ngram_matcher.match(merchant)
        if ngram_result:
            category, score = ngram_result
            return {
                "사용용도": category,
                "신뢰도": score,
                "라벨출처": "N-gram"
            }

        # 모든 매칭 실패
        return {
            "사용용도": None,
            "신뢰도": 0.0,
            "라벨출처": "미매칭"
        }

    def batch_match(self, merchants: pd.Series) -> pd.DataFrame:
        """
        배치 하이브리드 매칭

        Args:
            merchants: 가맹점명 Series

        Returns:
            DataFrame with columns: 사용용도, 신뢰도, 라벨출처
        """
        results = [self.match(m) for m in merchants]
        return pd.DataFrame(results)

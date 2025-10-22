"""
분류 파이프라인

전체 분류 프로세스를 통합 관리
"""
import pandas as pd
from pathlib import Path
from typing import Optional
from datetime import datetime

from .preprocessor import Preprocessor
from .matchers import HybridMatcher
from .claude_api import ClaudeClassifier, select_fewshot_examples
from .rules import PostProcessor


class CardClassifier:
    """
    법인카드 사용용도 자동분류 메인 클래스

    Phase 1: 전처리 + 룩업/유사 매칭
    Phase 2: Claude API 통합
    """

    def __init__(
        self,
        master_db_path: Path,
        synonym_map: dict = None,
        fuzzy_threshold: float = 0.85,
        ngram_threshold: float = 0.6,
        ngram_size: int = 3,
        enable_claude: bool = False,
        api_key: str = None
    ):
        """
        Args:
            master_db_path: 정답 DB 경로
            synonym_map: 유의어 사전
            fuzzy_threshold: Fuzzy 매칭 임계값
            ngram_threshold: N-gram 매칭 임계값
            ngram_size: N-gram 크기
            enable_claude: Claude API 사용 여부
            api_key: Claude API 키
        """
        # 정답 DB 로드
        self.master_db = self._load_master_db(master_db_path)

        # 모듈 초기화
        self.preprocessor = Preprocessor(synonym_map=synonym_map)
        self.matcher = HybridMatcher(
            master_db=self.master_db,
            fuzzy_threshold=fuzzy_threshold,
            ngram_threshold=ngram_threshold,
            ngram_size=ngram_size
        )

        # Claude API 초기화 (Phase 2)
        self.enable_claude = enable_claude
        if enable_claude:
            try:
                self.claude_classifier = ClaudeClassifier(api_key=api_key)
                self.post_processor = PostProcessor()
                print("✅ Claude API 활성화")
            except ValueError as e:
                print(f"⚠️  Claude API 비활성화: {e}")
                self.enable_claude = False
        else:
            self.claude_classifier = None
            self.post_processor = None

    def _load_master_db(self, path: Path) -> pd.DataFrame:
        """
        정답 DB 로드

        Args:
            path: CSV 파일 경로

        Returns:
            DataFrame with columns: 가맹점명, 사용용도
        """
        try:
            df = pd.read_csv(path, encoding="utf-8-sig")

            # 필수 컬럼 확인
            required_cols = ["가맹점명", "사용용도"]
            if not all(col in df.columns for col in required_cols):
                raise ValueError(f"정답 DB에 필수 컬럼 누락: {required_cols}")

            # 중복 제거 (첫 번째 항목 유지)
            df = df.drop_duplicates(subset=["가맹점명"], keep="first")

            # 가맹점명 전처리
            preprocessor = Preprocessor()
            df["가맹점명"] = df["가맹점명"].apply(preprocessor.normalize)

            return df

        except FileNotFoundError:
            raise FileNotFoundError(f"정답 DB 파일을 찾을 수 없습니다: {path}")

    def classify_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None
    ) -> pd.DataFrame:
        """
        카드사 명세서 파일 분류

        Args:
            input_path: 입력 파일 경로 (XLSX/CSV)
            output_path: 출력 파일 경로 (옵션)

        Returns:
            분류 결과 DataFrame
        """
        # 1. 파일 파싱
        print(f"파일 로드 중: {input_path}")
        df = self.preprocessor.parse_file(input_path)
        print(f"  → {len(df)}건 로드 완료")

        # 2. 전처리
        print("전처리 중...")
        df = self.preprocessor.preprocess_dataframe(df)

        # 3. 배치 분류
        print("분류 중...")
        result = self.classify_batch(df)

        # 4. 결과 저장
        if output_path:
            self._save_result(result, output_path)
            print(f"결과 저장 완료: {output_path}")

        # 5. 통계 출력
        self._print_statistics(result)

        return result

    def classify_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        배치 분류 실행

        Args:
            df: 전처리된 DataFrame

        Returns:
            분류 결과 DataFrame
        """
        results = []

        for idx, row in df.iterrows():
            # 컨텍스트 정보 준비
            try:
                amount = int(row["이용금액"]) if row["이용금액"] else 0
            except (ValueError, TypeError, KeyError):
                amount = 0

            try:
                date = str(row["승인일자"])
            except (TypeError, KeyError):
                date = ""

            context = {
                "승인일자": date,
                "이용금액": amount
            }

            # 단일 분류 실행 (Claude API 포함)
            result = self.classify_single(
                merchant=str(row["가맹점명_원본"]),
                context=context
            )

            results.append(result)

        # DataFrame 변환
        result_df = pd.DataFrame(results)

        # 컬럼 정리 (필요한 컬럼만 선택)
        output_cols = [
            "승인일자",
            "가맹점명_원본",
            "가맹점명",
            "이용금액",
            "사용용도",
            "신뢰도",
            "라벨출처"
        ]

        # 근거 컬럼이 있으면 추가
        if "근거" in result_df.columns:
            output_cols.append("근거")

        return result_df[output_cols]

    def classify_single(
        self,
        merchant: str,
        context: dict = None
    ) -> dict:
        """
        단일 가맹점 분류

        Args:
            merchant: 가맹점명
            context: 추가 컨텍스트 정보
                     {승인일자, 이용금액}

        Returns:
            분류 결과 딕셔너리
        """
        # 전처리
        normalized = self.preprocessor.normalize(merchant)

        # 1단계: 하이브리드 매칭 (정확/Fuzzy/N-gram)
        result = self.matcher.match(normalized)

        # 2단계: Claude API 예측 (미매칭 시)
        if result["라벨출처"] == "미매칭" and self.enable_claude:
            # Few-shot 예시 선정
            examples = select_fewshot_examples(
                self.master_db,
                n=5,
                strategy="diverse"
            )

            # Claude API 호출
            claude_result = self.claude_classifier.predict(
                merchant=normalized,
                examples=examples,
                context=context
            )

            # 3단계: 규칙 기반 후처리
            if self.post_processor:
                processed = self.post_processor.process(
                    merchant=normalized,
                    category=claude_result["사용용도"],
                    confidence=claude_result["신뢰도"],
                    context=context
                )

                result.update({
                    "사용용도": processed["category"],
                    "신뢰도": processed["confidence"],
                    "라벨출처": "Claude+규칙" if processed["rule_applied"] else "Claude",
                    "근거": claude_result["근거"],
                    "api_usage": claude_result.get("api_usage")
                })
            else:
                result.update({
                    "사용용도": claude_result["사용용도"],
                    "신뢰도": claude_result["신뢰도"],
                    "라벨출처": "Claude",
                    "근거": claude_result["근거"],
                    "api_usage": claude_result.get("api_usage")
                })

        # 컨텍스트 추가
        if context:
            for key, value in context.items():
                if key not in result:
                    result[key] = value

        result["가맹점명_원본"] = merchant
        result["가맹점명"] = normalized

        return result

    def _save_result(self, df: pd.DataFrame, output_path: Path):
        """
        결과 저장

        Args:
            df: 분류 결과 DataFrame
            output_path: 출력 파일 경로
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix == ".csv":
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
        elif output_path.suffix in [".xlsx", ".xls"]:
            df.to_excel(output_path, index=False)
        else:
            raise ValueError(f"지원하지 않는 출력 형식: {output_path.suffix}")

    def _print_statistics(self, df: pd.DataFrame):
        """
        분류 통계 출력

        Args:
            df: 분류 결과 DataFrame
        """
        print("\n=== 분류 통계 ===")
        print(f"총 거래 건수: {len(df)}건")

        # 라벨 출처별 통계
        print("\n[라벨 출처]")
        source_counts = df["라벨출처"].value_counts()
        for source, count in source_counts.items():
            pct = count / len(df) * 100
            print(f"  {source}: {count}건 ({pct:.1f}%)")

        # 미매칭 비율
        unmatched = len(df[df["라벨출처"] == "미매칭"])
        if unmatched > 0:
            print(f"\n⚠️  미매칭: {unmatched}건 ({unmatched/len(df)*100:.1f}%)")
            if not self.enable_claude:
                print("   → Claude API를 활성화하면 자동 분류 가능")

        # 신뢰도 분포
        matched_df = df[df["라벨출처"] != "미매칭"]
        if len(matched_df) > 0:
            print(f"\n[신뢰도 통계]")
            print(f"  평균: {matched_df['신뢰도'].mean():.3f}")
            print(f"  중간값: {matched_df['신뢰도'].median():.3f}")
            print(f"  최소: {matched_df['신뢰도'].min():.3f}")
            print(f"  최대: {matched_df['신뢰도'].max():.3f}")

        # Claude API 사용 통계
        if self.enable_claude and self.claude_classifier:
            stats = self.claude_classifier.get_stats()
            if stats["total_calls"] > 0:
                print(f"\n[Claude API 사용 현황]")
                print(f"  API 호출: {stats['total_calls']}건")
                print(f"  성공: {stats['successful_calls']}건")
                print(f"  실패: {stats['failed_calls']}건")
                print(f"  입력 토큰: {stats['total_input_tokens']:,}개")
                print(f"  출력 토큰: {stats['total_output_tokens']:,}개")
                print(f"  예상 비용: ${stats['estimated_cost_usd']:.4f}")

        # 사용용도별 통계 (상위 10개)
        print("\n[사용용도 Top 10]")
        category_counts = df[df["사용용도"].notna()]["사용용도"].value_counts().head(10)
        for category, count in category_counts.items():
            print(f"  {category}: {count}건")

    def get_unmatched(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        미매칭 거래 추출

        Args:
            df: 분류 결과 DataFrame

        Returns:
            미매칭 거래 DataFrame
        """
        return df[df["라벨출처"] == "미매칭"].copy()

    def export_for_feedback(
        self,
        df: pd.DataFrame,
        output_path: Path
    ):
        """
        피드백용 파일 생성

        검토 우선순위:
        1. 미매칭
        2. 낮은 신뢰도 (<0.8)

        Args:
            df: 분류 결과 DataFrame
            output_path: 출력 파일 경로
        """
        # 검토 필요 항목 추출
        review_needed = df[
            (df["라벨출처"] == "미매칭") |
            (df["신뢰도"] < 0.8)
        ].copy()

        # 우선순위 점수 계산 (낮을수록 우선)
        review_needed["검토우선순위"] = review_needed["신뢰도"]
        review_needed = review_needed.sort_values("검토우선순위")

        # 검토용 컬럼만 선택
        feedback_df = review_needed[[
            "승인일자",
            "가맹점명_원본",
            "이용금액",
            "사용용도",
            "신뢰도",
            "라벨출처",
            "검토우선순위"
        ]]

        # 확정용도 컬럼 추가 (수동 입력용)
        feedback_df["확정용도"] = ""

        # 저장
        self._save_result(feedback_df, output_path)
        print(f"\n피드백 파일 생성 완료: {output_path}")
        print(f"검토 필요 항목: {len(feedback_df)}건")

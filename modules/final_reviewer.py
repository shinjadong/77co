"""
최종 검토 및 결정 모듈

Claude AI가 분류 결과를 검토하고 최종 확정
"""
import pandas as pd
from pathlib import Path
from typing import Dict, List
import anthropic
import os


class FinalReviewer:
    """
    분류 결과 최종 검토 및 확정 클래스
    """

    REVIEW_SYSTEM_PROMPT = """당신은 칠칠기업의 법인카드 사용용도 분류 결과를 검토하고 최종 확정하는 전문가입니다.

<role>
자동 분류 시스템의 결과를 검토하여:
1. 낮은 신뢰도 거래의 분류 적절성 평가
2. 의심스러운 분류 발견 및 수정
3. 최종 확정 또는 추가 검토 필요 여부 결정
</role>

<review_criteria>
1. 가맹점명과 사용용도의 일치성
2. 신뢰도와 실제 분류 정확성의 일관성
3. 규칙 엔진과 AI 예측 간 충돌 검토
4. 비정상 패턴 탐지 (금액 0원, 결측값 등)
</review_criteria>

<decision_types>
- CONFIRM: 분류가 적절함, 확정
- MODIFY: 분류 수정 필요, 새로운 카테고리 제안
- REVIEW: 수동 검토 필요 (판단 어려움)
</decision_types>

<output_format>
각 거래에 대해 다음 형식으로 응답:

<review>
  <decision>CONFIRM|MODIFY|REVIEW</decision>
  <final_category>최종 사용용도</final_category>
  <final_confidence>0.0~1.0</final_confidence>
  <reason>결정 근거 (1-2문장)</reason>
</review>

여러 거래를 검토할 때는 <reviews> 태그로 감싸세요.
</output_format>
"""

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: Anthropic API 키
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def review_results(
        self,
        results_df: pd.DataFrame,
        review_threshold: float = 0.8
    ) -> pd.DataFrame:
        """
        분류 결과 전체 검토

        Args:
            results_df: 분류 결과 DataFrame
            review_threshold: 검토 대상 신뢰도 임계값

        Returns:
            검토 완료된 DataFrame
        """
        # 검토 대상 추출 (낮은 신뢰도 또는 특정 조건)
        review_needed = results_df[
            (results_df["신뢰도"] < review_threshold) |
            (results_df["라벨출처"] == "미매칭") |
            (results_df["사용용도"] == "기타")
        ].copy()

        if len(review_needed) == 0:
            print("검토 필요 항목 없음 - 모두 확정")
            results_df["최종확정"] = "자동확정"
            results_df["검토의견"] = ""
            return results_df

        print(f"\n검토 대상: {len(review_needed)}건")

        # Claude API로 일괄 검토
        reviews = self._batch_review(review_needed)

        # 검토 결과 병합
        final_df = results_df.copy()
        final_df["최종확정"] = "자동확정"
        final_df["최종사용용도"] = final_df["사용용도"]
        final_df["최종신뢰도"] = final_df["신뢰도"]
        final_df["검토의견"] = ""

        # 검토 결과 적용
        for idx, review in reviews.items():
            if review["decision"] == "MODIFY":
                final_df.loc[idx, "최종사용용도"] = review["final_category"]
                final_df.loc[idx, "최종신뢰도"] = review["final_confidence"]
                final_df.loc[idx, "최종확정"] = "AI수정"
            elif review["decision"] == "REVIEW":
                final_df.loc[idx, "최종확정"] = "수동검토필요"
            else:  # CONFIRM
                final_df.loc[idx, "최종확정"] = "AI확정"

            final_df.loc[idx, "검토의견"] = review["reason"]

        return final_df

    def _batch_review(
        self,
        df: pd.DataFrame,
        batch_size: int = 10
    ) -> Dict:
        """
        배치 검토 실행

        Args:
            df: 검토 대상 DataFrame
            batch_size: 배치 크기

        Returns:
            {index: review_result}
        """
        reviews = {}

        # 배치 단위로 처리
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i + batch_size]
            batch_reviews = self._review_batch(batch)
            reviews.update(batch_reviews)

        return reviews

    def _review_batch(self, batch_df: pd.DataFrame) -> Dict:
        """
        배치 검토 API 호출

        Args:
            batch_df: 검토 대상 배치

        Returns:
            검토 결과
        """
        # 프롬프트 생성
        transactions_text = ""
        for idx, row in batch_df.iterrows():
            # 일자 컬럼 확인
            date_col = "결제일자" if "결제일자" in row else "승인일자"
            date_value = row.get(date_col, "")

            transactions_text += f"""
<transaction id="{idx}">
  <merchant>{row['가맹점명_원본']}</merchant>
  <predicted_category>{row['사용용도']}</predicted_category>
  <confidence>{row['신뢰도']}</confidence>
  <source>{row['라벨출처']}</source>
  <date>{date_value}</date>
  <amount>{row['이용금액']}</amount>
</transaction>
"""

        user_prompt = f"""다음 거래들의 분류 결과를 검토하고, 각 거래에 대해 결정을 내려주세요:

<transactions>
{transactions_text}
</transactions>

각 거래(id 포함)에 대해 <review> 형식으로 응답하고, 모두 <reviews> 태그로 감싸주세요.
"""

        try:
            # API 호출
            message = self.client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4000,
                temperature=0.1,
                system=self.REVIEW_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}]
            )

            response_text = message.content[0].text
            return self._parse_reviews(response_text)

        except Exception as e:
            print(f"검토 API 오류: {e}")
            # 오류 시 모두 CONFIRM으로 처리
            return {
                idx: {
                    "decision": "CONFIRM",
                    "final_category": row["사용용도"],
                    "final_confidence": row["신뢰도"],
                    "reason": "API 오류로 자동 확정"
                }
                for idx, row in batch_df.iterrows()
            }

    def _parse_reviews(self, response: str) -> Dict:
        """
        검토 응답 파싱

        Args:
            response: Claude 응답

        Returns:
            {index: review_result}
        """
        import re
        import xml.etree.ElementTree as ET

        reviews = {}

        # <review> 태그들 추출
        review_pattern = r'<review[^>]*>(.*?)</review>'
        review_matches = re.findall(review_pattern, response, re.DOTALL)

        for review_text in review_matches:
            try:
                # id 추출 (transaction id 참조)
                # <review> 태그 앞뒤 컨텍스트에서 id 찾기
                review_xml = f"<review>{review_text}</review>"
                root = ET.fromstring(review_xml)

                # 거래 인덱스 찾기 (response에서 id 추출)
                # 간단히 순서대로 할당 (개선 가능)
                idx = len(reviews)

                decision = root.find("decision")
                final_category = root.find("final_category")
                final_confidence = root.find("final_confidence")
                reason = root.find("reason")

                reviews[idx] = {
                    "decision": decision.text.strip() if decision is not None else "CONFIRM",
                    "final_category": final_category.text.strip() if final_category is not None else "",
                    "final_confidence": float(final_confidence.text.strip()) if final_confidence is not None else 0.0,
                    "reason": reason.text.strip() if reason is not None else ""
                }

            except Exception as e:
                continue

        return reviews

    def create_final_output(
        self,
        reviewed_df: pd.DataFrame,
        output_path: Path = None,
        card_number: str = "3987"
    ):
        """
        최종 확정 파일 생성

        Args:
            reviewed_df: 검토 완료된 DataFrame
            output_path: 출력 경로 (None이면 자동 생성)
            card_number: 카드번호 (파일명용)
        """
        # 결제일자에서 월 추출
        month = self._extract_month(reviewed_df)

        # 출력 경로 자동 생성
        if output_path is None:
            output_path = Path(f"output/법인카드_({month})월_{card_number}.csv")
        elif "{month}" in str(output_path):
            # 경로에 {month} 플레이스홀더가 있으면 치환
            output_path = Path(str(output_path).replace("{month}", str(month)))
        # 최종 출력 컬럼 선택
        output_df = pd.DataFrame()

        # 원본 정보
        date_col = "결제일자" if "결제일자" in reviewed_df.columns else "승인일자"
        output_df["결제일자"] = reviewed_df[date_col]
        output_df["가맹점명"] = reviewed_df["가맹점명_원본"]
        output_df["이용금액"] = reviewed_df["이용금액"]

        # 최종 확정 사용용도
        output_df["사용용도"] = reviewed_df["최종사용용도"]

        # 메타 정보
        output_df["신뢰도"] = reviewed_df["최종신뢰도"]
        output_df["확정방법"] = reviewed_df["최종확정"]

        # 검토 의견 (있는 경우만)
        if "검토의견" in reviewed_df.columns:
            has_opinion = reviewed_df["검토의견"].notna() & (reviewed_df["검토의견"] != "")
            if has_opinion.any():
                output_df["검토의견"] = reviewed_df["검토의견"]

        # 결측값 제거
        output_df = output_df[output_df["가맹점명"].notna()].copy()

        # 저장
        if output_path.suffix == ".csv":
            output_df.to_csv(output_path, index=False, encoding="utf-8-sig")
        elif output_path.suffix in [".xlsx", ".xls"]:
            output_df.to_excel(output_path, index=False)

        print(f"\n최종 파일 생성: {output_path}")
        print(f"  총 거래: {len(output_df)}건")

        # 통계
        print("\n[확정 방법별 통계]")
        print(output_df["확정방법"].value_counts())

        return output_df

    def _extract_month(self, df: pd.DataFrame) -> int:
        """
        DataFrame에서 주요 월 추출

        Args:
            df: DataFrame (결제일자 컬럼 포함)

        Returns:
            월 (1~12)
        """
        # 결제일자를 datetime으로 변환
        date_col = "결제일자" if "결제일자" in df.columns else "승인일자"
        dates = pd.to_datetime(df[date_col], errors='coerce')

        # 결측값 제거
        valid_dates = dates.dropna()

        if len(valid_dates) == 0:
            # 일자가 없으면 현재 월 반환
            return datetime.now().month

        # 월 추출 및 최빈값 계산
        months = valid_dates.dt.month
        most_common_month = months.mode()[0] if len(months.mode()) > 0 else months.iloc[0]

        return int(most_common_month)

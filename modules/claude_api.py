"""
Claude API 통합 모듈

가맹점명 분류를 위한 Claude API 인터페이스
"""
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
import anthropic


class ClaudeClassifier:
    """
    Claude API 기반 가맹점 분류 클래스
    """

    # 시스템 프롬프트
    SYSTEM_PROMPT = """당신은 칠칠기업의 법인카드 거래내역 사용용도 자동분류 전문가입니다.

<role>
가맹점명, 승인일자, 이용금액 정보를 분석하여 사내 분류 체계에 따라
정확한 '사용용도' 카테고리를 예측합니다.
</role>

<expertise>
- 한국어 상호명 및 브랜드 패턴 이해
- 업종별 키워드 인식 (주유소, 음식점, 소프트웨어 등)
- 금액 패턴 분석 (주유비, 식대, 소모품 등)
- 컨텍스트 기반 추론 (일자, 금액과 용도의 관계)
</expertise>

<classification_system>
칠칠기업은 다음과 같은 사용용도 체계를 사용합니다:

1. 차량유지비(주유)
   - 주유소 관련: GS칼텍스, S-OIL, 오일뱅크, SK에너지, 현대오일, 효창에너지 등
   - 키워드: 주유소, 주유, 경유, 휘발유, 셀프주유 등

2. 차량유지비(기타)
   - 통행료: 하이패스, 톨게이트, IC주유소(통행), 고속도로 등
   - 주차: 주차장, 파킹, 주차비 등
   - 세차: 세차장, 세차 등
   - 정비: 자동차정비, 자동차검사, 타이어 등

3. 중식대
   - 음식점: 식당, 한식, 중식, 일식, 양식, 분식 등
   - 패스트푸드: 맥도날드, 롯데리아, 버거킹, 써브웨이 등
   - 카페: 스타벅스, 이디야, 커피, 카페 등
   - 편의점: CU, GS25, 세븐일레븐 등 (식품 구매)

4. 사용료
   - 소프트웨어: 한글과컴퓨터, Microsoft, Adobe, 오피스365 등
   - 클라우드: AWS, 네이버클라우드, 카카오클라우드 등
   - 통신: 휴대폰, 인터넷, 메시지 등
   - 자동결제 서비스 전반

5. 복리후생비(의료)
   - 의료기관: 병원, 의원, 한의원, 치과 등
   - 약국: 약국 등

6. 소모품비
   - 문구/사무용품: 다이소, 오피스디포, 모닝글로리 등
   - 온라인쇼핑: 쿠팡, 이마트, 홈플러스 등 (소모품)
   - 키워드: 문구, 토너, 잉크, 복사용지, 비품 등

7. 수수료
   - 금융: 은행, 보증보험, 기술보증기금 등
   - 법무: 법원, 등기소 등
   - 우편: 우체국, 우편료 등

8. 세금
   - 국세청: 부가가치세, 법인세 등
   - 지방세: 자동차세, 재산세 등

9. 기타
   - 위 카테고리에 명확히 해당하지 않는 경우
   - 판단이 어려운 경우
</classification_system>

<guidelines>
1. 가맹점명의 핵심 키워드를 정확히 식별하세요
2. 업종이 명확하지 않으면 금액과 일자 패턴을 참고하세요
3. 예시 데이터를 참고하되, 기계적 매칭이 아닌 의미론적 이해를 우선하세요
4. 확신이 서지 않으면 낮은 신뢰도를 부여하세요
5. 반드시 기존 카테고리 중 하나를 선택하세요 (새 카테고리 생성 금지)
</guidelines>

<output_requirements>
반드시 다음 XML 형식으로 응답하세요. 다른 텍스트는 포함하지 마세요:

<prediction>
  <category>사용용도 카테고리</category>
  <confidence>0.0~1.0 사이의 신뢰도 (소수점 2자리)</confidence>
  <reasoning>예측 근거를 1-2문장으로 간결하게</reasoning>
</prediction>

신뢰도 기준:
- 0.9 이상: 매우 확실 (명확한 키워드 매칭)
- 0.7~0.9: 확실 (업종 추론 가능)
- 0.5~0.7: 보통 (일부 불확실성 존재)
- 0.5 미만: 불확실 (추가 확인 필요)
</output_requirements>
"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-5",
        max_tokens: int = 1000,
        temperature: float = 0.2
    ):
        """
        Args:
            api_key: Anthropic API 키 (None이면 환경변수에서 로드)
            model: 사용할 Claude 모델
            max_tokens: 최대 생성 토큰 수
            temperature: 생성 온도 (0~1, 낮을수록 일관적)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
                "환경변수를 설정하거나 api_key 파라미터를 전달하세요."
            )

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # API 호출 통계
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }

    def predict(
        self,
        merchant: str,
        examples: List[Dict],
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Claude API를 통한 가맹점 분류

        Args:
            merchant: 정규화된 가맹점명
            examples: Few-shot 예시 리스트
            context: 추가 컨텍스트 {승인일자, 이용금액}

        Returns:
            {
                "사용용도": str,
                "신뢰도": float,
                "근거": str,
                "api_usage": {...}
            }
        """
        # 사용자 프롬프트 구성
        user_prompt = self._build_user_prompt(merchant, examples, context)

        try:
            # API 호출
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )

            # 통계 업데이트
            self.stats["total_calls"] += 1
            self.stats["total_input_tokens"] += message.usage.input_tokens
            self.stats["total_output_tokens"] += message.usage.output_tokens

            # 응답 파싱
            response_text = message.content[0].text
            result = self._parse_response(response_text)

            # API 사용량 정보 추가
            result["api_usage"] = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
                "model": self.model
            }

            self.stats["successful_calls"] += 1
            return result

        except Exception as e:
            self.stats["failed_calls"] += 1
            return {
                "사용용도": "미분류",
                "신뢰도": 0.0,
                "근거": f"API 오류: {str(e)}",
                "api_usage": None
            }

    def _build_user_prompt(
        self,
        merchant: str,
        examples: List[Dict],
        context: Optional[Dict] = None
    ) -> str:
        """
        사용자 프롬프트 생성

        Args:
            merchant: 가맹점명
            examples: Few-shot 예시
            context: 추가 컨텍스트

        Returns:
            프롬프트 문자열
        """
        # Few-shot 예시 포맷팅
        examples_text = "\n".join([
            f"<example>\n"
            f"  <merchant>{ex['merchant']}</merchant>\n"
            f"  <category>{ex['category']}</category>\n"
            f"</example>"
            for ex in examples
        ])

        # 컨텍스트 정보
        date = context.get("승인일자", "") if context else ""
        amount = context.get("이용금액", "") if context else ""

        prompt = f"""<examples>
{examples_text}
</examples>

<task>
다음 법인카드 거래의 사용용도를 예측해주세요:

<transaction>
  <merchant>{merchant}</merchant>
  <date>{date}</date>
  <amount>{amount}원</amount>
</transaction>

위 거래의 사용용도를 예측하고, 신뢰도와 근거를 제시해주세요.
</task>
"""
        return prompt

    def _parse_response(self, response: str) -> Dict:
        """
        Claude 응답 XML 파싱

        Args:
            response: Claude의 XML 응답

        Returns:
            {
                "사용용도": str,
                "신뢰도": float,
                "근거": str
            }
        """
        try:
            # 응답 정리
            response = response.strip()

            # <prediction> 태그 추출
            if "<prediction>" in response:
                start = response.find("<prediction>")
                end = response.find("</prediction>") + len("</prediction>")
                if start >= 0 and end > start:
                    response = response[start:end]

            # XML 파싱
            root = ET.fromstring(response)

            category = root.find("category")
            confidence = root.find("confidence")
            reasoning = root.find("reasoning")

            return {
                "사용용도": category.text.strip() if category is not None and category.text else "미분류",
                "신뢰도": float(confidence.text.strip()) if confidence is not None and confidence.text else 0.0,
                "근거": reasoning.text.strip() if reasoning is not None and reasoning.text else "근거 없음"
            }

        except Exception as e:
            # 파싱 실패 시 텍스트 분석 시도
            return self._fallback_parse(response, e)

    def _fallback_parse(self, response: str, error: Exception) -> Dict:
        """
        XML 파싱 실패 시 대체 파싱

        Args:
            response: 응답 텍스트
            error: 원본 오류

        Returns:
            기본 결과
        """
        import re

        category = "미분류"
        confidence = 0.0
        reasoning = ""

        # 정규식으로 태그 내용 추출 시도
        category_match = re.search(r'<category>\s*([^<]+?)\s*</category>', response, re.DOTALL)
        if category_match:
            category = category_match.group(1).strip()

        confidence_match = re.search(r'<confidence>\s*([\d.]+)\s*</confidence>', response, re.DOTALL)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
            except ValueError:
                confidence = 0.0

        reasoning_match = re.search(r'<reasoning>\s*([^<]+?)\s*</reasoning>', response, re.DOTALL)
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()

        # 여전히 실패하면 줄별 분석
        if category == "미분류":
            lines = response.split('\n')
            for line in lines:
                if "category" in line.lower() and ">" in line:
                    match = re.search(r'>([^<]+)<', line)
                    if match:
                        category = match.group(1).strip()
                elif "confidence" in line.lower() and ">" in line:
                    match = re.search(r'>([\d.]+)<', line)
                    if match:
                        try:
                            confidence = float(match.group(1))
                        except ValueError:
                            pass

        # 근거가 비어있으면 오류 메시지
        if not reasoning:
            reasoning = f"XML 파싱 실패 (대체 파싱 사용): {str(error)[:100]}"

        return {
            "사용용도": category,
            "신뢰도": confidence,
            "근거": reasoning
        }

    def get_stats(self) -> Dict:
        """
        API 사용 통계 반환

        Returns:
            통계 딕셔너리
        """
        stats = self.stats.copy()

        # 비용 추정 (대략적인 값)
        # Claude Sonnet 4.5: $3/MTok input, $15/MTok output
        input_cost = (stats["total_input_tokens"] / 1_000_000) * 3
        output_cost = (stats["total_output_tokens"] / 1_000_000) * 15
        total_cost = input_cost + output_cost

        stats["estimated_cost_usd"] = round(total_cost, 4)
        stats["avg_input_tokens"] = (
            stats["total_input_tokens"] / stats["total_calls"]
            if stats["total_calls"] > 0 else 0
        )
        stats["avg_output_tokens"] = (
            stats["total_output_tokens"] / stats["total_calls"]
            if stats["total_calls"] > 0 else 0
        )

        return stats

    def reset_stats(self):
        """통계 초기화"""
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }


def select_fewshot_examples(
    master_db,
    n: int = 5,
    strategy: str = "diverse"
) -> List[Dict]:
    """
    Few-shot 예시 선정

    Args:
        master_db: 정답 DB DataFrame
        n: 선택할 예시 개수
        strategy: 선정 전략
                  - "diverse": 카테고리별 균형
                  - "random": 랜덤
                  - "recent": 최신 데이터 우선

    Returns:
        예시 리스트
    """
    import pandas as pd

    if strategy == "diverse":
        # 카테고리별로 균등하게 샘플링
        examples = []
        categories = master_db["사용용도"].unique()

        samples_per_category = max(1, n // len(categories))

        for category in categories:
            category_df = master_db[master_db["사용용도"] == category]
            samples = category_df.sample(
                min(samples_per_category, len(category_df))
            )

            for _, row in samples.iterrows():
                examples.append({
                    "merchant": row["가맹점명"],
                    "category": row["사용용도"]
                })

            if len(examples) >= n:
                break

        return examples[:n]

    elif strategy == "random":
        # 랜덤 샘플링
        samples = master_db.sample(min(n, len(master_db)))
        return [
            {
                "merchant": row["가맹점명"],
                "category": row["사용용도"]
            }
            for _, row in samples.iterrows()
        ]

    else:
        raise ValueError(f"알 수 없는 전략: {strategy}")

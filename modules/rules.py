"""
규칙 기반 보정 엔진

키워드 사전 기반 후처리 및 검증
"""
import re
from typing import Optional, Dict, List


class RuleEngine:
    """
    규칙 기반 사용용도 보정 엔진
    """

    def __init__(self, keyword_rules: Dict[str, List[str]] = None):
        """
        Args:
            keyword_rules: 카테고리별 키워드 사전
                           {카테고리: [키워드 리스트]}
        """
        self.keyword_rules = keyword_rules or self._get_default_rules()

    def _get_default_rules(self) -> Dict[str, List[str]]:
        """
        기본 키워드 규칙 반환
        """
        return {
            "차량유지비(주유)": [
                "주유소", "GS칼텍스", "S-OIL", "오일뱅크", "SK에너지",
                "현대오일", "효창에너지", "셀프주유", "경유", "휘발유",
                "칼텍스", "에너지", "오일", "주유"
            ],
            "차량유지비(기타)": [
                "하이패스", "톨게이트", "IC주유소", "주차", "세차",
                "자동차정비", "자동차검사", "타이어", "통행",
                "파킹", "주차장"
            ],
            "중식대": [
                "맥도날드", "롯데리아", "버거킹", "써브웨이", "서브웨이",
                "스타벅스", "이디야", "커피", "카페", "식당", "반점",
                "중화요리", "순대국", "설렁탕", "본죽", "김밥",
                "떡볶이", "라면", "국수", "밥", "돈까스", "치킨"
            ],
            "사용료": [
                "한글과컴퓨터", "Microsoft", "Adobe", "오피스365",
                "AWS", "클라우드", "자동결제", "휴대폰", "메시지",
                "구독", "정기결제"
            ],
            "복리후생비(의료)": [
                "약국", "병원", "의원", "한의원", "치과", "의료"
            ],
            "소모품비": [
                "다이소", "문구", "토너", "잉크", "복사용지",
                "쿠팡", "이마트", "홈플러스", "비품", "사무용품"
            ],
            "수수료": [
                "보증보험", "기술보증기금", "법원", "우체국",
                "수수료", "보증료"
            ],
            "세금": [
                "국세", "부가가치세", "법인세", "지방세",
                "자동차세", "재산세", "세금"
            ]
        }

    def validate(
        self,
        merchant: str,
        predicted_category: str,
        confidence: float = 1.0
    ) -> Dict:
        """
        예측 결과 검증 및 보정

        Args:
            merchant: 가맹점명
            predicted_category: 예측된 카테고리
            confidence: 예측 신뢰도

        Returns:
            {
                "category": str,  # 최종 카테고리
                "confidence": float,  # 조정된 신뢰도
                "rule_applied": bool,  # 규칙 적용 여부
                "original_category": str  # 원본 카테고리
            }
        """
        # 규칙 매칭 시도
        rule_category = self._match_keywords(merchant)

        if rule_category is None:
            # 규칙 매칭 실패 - 원본 예측 유지
            return {
                "category": predicted_category,
                "confidence": confidence,
                "rule_applied": False,
                "original_category": predicted_category
            }

        # 규칙 매칭 성공
        if rule_category == predicted_category:
            # 예측과 규칙이 일치 - 신뢰도 상승
            return {
                "category": predicted_category,
                "confidence": min(1.0, confidence + 0.1),  # 최대 10% 상승
                "rule_applied": True,
                "original_category": predicted_category
            }
        else:
            # 예측과 규칙이 불일치
            if confidence < 0.7:
                # 낮은 신뢰도면 규칙 우선
                return {
                    "category": rule_category,
                    "confidence": 0.8,  # 규칙 기반 신뢰도
                    "rule_applied": True,
                    "original_category": predicted_category
                }
            else:
                # 높은 신뢰도면 예측 우선
                return {
                    "category": predicted_category,
                    "confidence": confidence,
                    "rule_applied": False,
                    "original_category": predicted_category
                }

    def _match_keywords(self, merchant: str) -> Optional[str]:
        """
        키워드 매칭 (우선순위 적용)

        Args:
            merchant: 가맹점명

        Returns:
            매칭된 카테고리 or None
        """
        merchant_lower = merchant.lower()

        # 🔴 최우선 규칙: "주유소" 키워드
        if "주유소" in merchant_lower:
            return "차량유지비(주유)"

        # 일반 카테고리별 키워드 확인
        for category, keywords in self.keyword_rules.items():
            for keyword in keywords:
                keyword_lower = keyword.lower()

                # 정확 매칭 또는 부분 매칭
                if keyword_lower in merchant_lower:
                    return category

        return None

    def apply_amount_rules(
        self,
        merchant: str,
        category: str,
        amount: int
    ) -> Dict:
        """
        금액 기반 규칙 적용

        Args:
            merchant: 가맹점명
            category: 현재 카테고리
            amount: 거래 금액

        Returns:
            조정된 결과
        """
        # 금액 패턴 분석
        if amount > 0:
            # 주유비 패턴 (보통 5만원 이상)
            if amount >= 50000 and "주유" in merchant:
                if category != "차량유지비(주유)":
                    return {
                        "category": "차량유지비(주유)",
                        "confidence": 0.75,
                        "rule_applied": True,
                        "rule_type": "amount_pattern"
                    }

            # 식대 패턴 (보통 3만원 이하)
            if amount <= 30000 and any(k in merchant for k in ["식당", "카페", "커피"]):
                if category != "중식대":
                    return {
                        "category": "중식대",
                        "confidence": 0.75,
                        "rule_applied": True,
                        "rule_type": "amount_pattern"
                    }

        # 규칙 미적용
        return {
            "category": category,
            "confidence": 1.0,
            "rule_applied": False,
            "rule_type": None
        }

    def get_category_hints(self, merchant: str) -> List[str]:
        """
        가능한 카테고리 힌트 제공

        Args:
            merchant: 가맹점명

        Returns:
            가능성 있는 카테고리 리스트
        """
        hints = []
        merchant_lower = merchant.lower()

        for category, keywords in self.keyword_rules.items():
            for keyword in keywords:
                if keyword.lower() in merchant_lower:
                    if category not in hints:
                        hints.append(category)

        return hints


class PostProcessor:
    """
    분류 결과 후처리 클래스
    """

    def __init__(self, rule_engine: RuleEngine = None):
        """
        Args:
            rule_engine: 규칙 엔진 인스턴스
        """
        self.rule_engine = rule_engine or RuleEngine()

    def process(
        self,
        merchant: str,
        category: str,
        confidence: float,
        context: Dict = None
    ) -> Dict:
        """
        종합 후처리

        Args:
            merchant: 가맹점명
            category: 예측 카테고리
            confidence: 신뢰도
            context: 추가 컨텍스트 {승인일자, 이용금액}

        Returns:
            최종 결과
        """
        # 1. 키워드 규칙 검증
        result = self.rule_engine.validate(
            merchant=merchant,
            predicted_category=category,
            confidence=confidence
        )

        # 2. 금액 규칙 적용 (컨텍스트 있을 때만)
        if context and "이용금액" in context:
            amount = context["이용금액"]
            amount_result = self.rule_engine.apply_amount_rules(
                merchant=merchant,
                category=result["category"],
                amount=amount
            )

            if amount_result["rule_applied"]:
                result = amount_result

        return result

#!/usr/bin/env python3
"""
법인카드 사용용도 AI 자동분류 프로그램

메인 실행 파일
"""
import argparse
from pathlib import Path
from datetime import datetime
import pandas as pd

import config
from modules.classifier import CardClassifier
from modules.final_reviewer import FinalReviewer
from modules.feedback import FeedbackManager


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(
        description="법인카드 사용용도 자동분류 프로그램"
    )

    parser.add_argument(
        "command",
        choices=["classify", "test", "finalize", "feedback"],
        help="실행할 명령"
    )

    parser.add_argument(
        "--input",
        "-i",
        type=str,
        help="입력 파일 경로 (XLSX/CSV)"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="출력 파일 경로 (옵션)"
    )

    parser.add_argument(
        "--feedback",
        action="store_true",
        help="피드백용 파일도 생성"
    )

    parser.add_argument(
        "--claude",
        action="store_true",
        help="Claude API 활성화 (미매칭 거래 자동 분류)"
    )

    parser.add_argument(
        "--card",
        type=str,
        default="3987",
        help="카드번호 (파일명에 사용, 기본값: 3987)"
    )

    args = parser.parse_args()

    if args.command == "classify":
        run_classify(args)
    elif args.command == "test":
        run_test(args)
    elif args.command == "finalize":
        run_finalize(args)
    elif args.command == "feedback":
        run_feedback(args)


def run_classify(args):
    """분류 실행"""
    if not args.input:
        print("오류: --input 옵션이 필요합니다")
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}")
        return

    # 출력 경로 설정
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = config.OUTPUT_DIR / f"분류결과_{timestamp}.csv"

    # 분류기 초기화
    print("분류기 초기화 중...")
    classifier = CardClassifier(
        master_db_path=config.MASTER_DB_PATH,
        synonym_map=config.SYNONYM_MAP,
        fuzzy_threshold=config.FUZZY_THRESHOLD,
        ngram_size=config.NGRAM_SIZE,
        enable_claude=args.claude,
        api_key=config.ANTHROPIC_API_KEY
    )

    # 분류 실행
    print(f"\n{'='*50}")
    print("분류 시작")
    print(f"{'='*50}\n")

    result = classifier.classify_file(
        input_path=input_path,
        output_path=output_path
    )

    # 피드백 파일 생성
    if args.feedback:
        feedback_path = output_path.parent / f"피드백_{output_path.stem}.csv"
        classifier.export_for_feedback(result, feedback_path)

    print(f"\n{'='*50}")
    print("분류 완료")
    print(f"{'='*50}\n")


def run_finalize(args):
    """최종 검토 및 확정 실행"""
    if not args.input:
        print("오류: --input 옵션이 필요합니다 (분류 결과 CSV 파일)")
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}")
        return

    # 출력 경로 설정 (월은 동적으로 추출)
    if args.output:
        output_path = Path(args.output)
    else:
        # 기본 형식: 법인카드_({month})월_3987.csv (월은 자동 추출)
        output_path = None  # FinalReviewer에서 자동 생성

    print("\n" + "="*50)
    print("최종 검토 시작")
    print("="*50 + "\n")
    print(f"입력: {input_path}")

    # 분류 결과 로드
    results_df = pd.read_csv(input_path, encoding="utf-8-sig")
    print(f"  → {len(results_df)}건 로드")

    # 검토기 초기화
    reviewer = FinalReviewer(api_key=config.ANTHROPIC_API_KEY)

    # 검토 실행
    print("\nClaude AI 검토 중...")
    reviewed_df = reviewer.review_results(results_df, review_threshold=0.8)

    # 카드번호 추출 (옵션에서 또는 파일명에서)
    card_number = getattr(args, 'card', '3987')

    # 최종 파일 생성
    print("\n최종 파일 생성 중...")
    final_df = reviewer.create_final_output(
        reviewed_df=reviewed_df,
        output_path=output_path,
        card_number=card_number
    )

    print(f"\n{'='*50}")
    print("최종 확정 완료")
    print(f"{'='*50}\n")


def run_feedback(args):
    """피드백 수집 및 DB 업데이트"""
    if not args.input:
        print("오류: --input 옵션이 필요합니다 (피드백 파일)")
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}")
        return

    print("\n" + "="*50)
    print("피드백 수집 시작")
    print("="*50 + "\n")

    # 피드백 관리자 초기화
    manager = FeedbackManager(
        master_db_path=config.MASTER_DB_PATH
    )

    # 피드백 수집 및 DB 업데이트
    result = manager.collect_feedback(
        feedback_file=input_path,
        auto_update=True
    )

    print(f"\n{'='*50}")
    print("피드백 처리 완료")
    print(f"{'='*50}\n")
    print(f"신규 추가: {result['new_entries']}건")
    print(f"기존 업데이트: {result['updated_entries']}건")

    if result['errors']:
        print("\n⚠️  오류:")
        for error in result['errors']:
            print(f"  - {error}")

    # 재학습 트리거 확인
    if manager.check_retrain_trigger():
        print("\n📊 재학습 권장: 신규 데이터 50건 이상 누적")


def run_test(args):
    """테스트 실행"""
    print("Phase 1 기능 테스트\n")

    # 분류기 초기화
    classifier = CardClassifier(
        master_db_path=config.MASTER_DB_PATH,
        synonym_map=config.SYNONYM_MAP
    )

    # 테스트 케이스
    test_cases = [
        {
            "merchant": "(주)삼원기업",
            "expected": "9315호 휘발유대"
        },
        {
            "merchant": "맥도날드 안산고잔DT점",
            "expected": "중식대"
        },
        {
            "merchant": "쿠팡(주)-쿠팡(주)",
            "expected": "회사물품구입비"
        },
        {
            "merchant": "새로운 가맹점 (미등록)",
            "expected": None
        }
    ]

    print("=" * 60)
    for i, case in enumerate(test_cases, 1):
        merchant = case["merchant"]
        expected = case["expected"]

        result = classifier.classify_single(merchant)

        print(f"\n테스트 {i}:")
        print(f"  입력: {merchant}")
        print(f"  정규화: {result['가맹점명']}")
        print(f"  예측: {result['사용용도']}")
        print(f"  신뢰도: {result['신뢰도']:.3f}")
        print(f"  출처: {result['라벨출처']}")

        if expected:
            status = "✅ 통과" if result['사용용도'] == expected else "❌ 실패"
            print(f"  상태: {status}")
        else:
            status = "✅ 통과" if result['사용용도'] is None else "❌ 실패"
            print(f"  상태: {status} (미매칭 예상)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()

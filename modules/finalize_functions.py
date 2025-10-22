"""
최종 확정 기능 함수들
"""
import pandas as pd
from pathlib import Path
from datetime import datetime


def run_finalize(args, config, FinalReviewer):
    """최종 검토 및 확정 실행"""
    if not args.input:
        print("오류: --input 옵션이 필요합니다 (분류 결과 CSV 파일)")
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}")
        return

    # 출력 경로 설정
    if args.output:
        output_path = Path(args.output)
    else:
        # 기본 형식: 법인카드_(8)월_3987.csv
        output_path = Path("output/법인카드_(8)월_3987.csv")

    print("최종 검토 시작...")
    print(f"입력: {input_path}")

    # 분류 결과 로드
    results_df = pd.read_csv(input_path, encoding="utf-8-sig")
    print(f"  → {len(results_df)}건 로드")

    # 검토기 초기화
    reviewer = FinalReviewer(api_key=config.ANTHROPIC_API_KEY)

    # 검토 실행
    print("\nClaude AI 검토 중...")
    reviewed_df = reviewer.review_results(results_df, review_threshold=0.8)

    # 최종 파일 생성
    print("\n최종 파일 생성 중...")
    final_df = reviewer.create_final_output(
        reviewed_df=reviewed_df,
        output_path=output_path,
        month=8
    )

    print(f"\n✅ 최종 확정 완료: {output_path}")


def run_feedback(args, config, FeedbackManager):
    """피드백 수집 및 DB 업데이트"""
    if not args.input:
        print("오류: --input 옵션이 필요합니다 (피드백 파일)")
        return

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"오류: 입력 파일을 찾을 수 없습니다: {input_path}")
        return

    print("피드백 수집 시작...")

    # 피드백 관리자 초기화
    manager = FeedbackManager(
        master_db_path=config.MASTER_DB_PATH
    )

    # 피드백 수집 및 DB 업데이트
    result = manager.collect_feedback(
        feedback_file=input_path,
        auto_update=True
    )

    print(f"\n✅ 피드백 처리 완료")
    print(f"  신규 추가: {result['new_entries']}건")
    print(f"  기존 업데이트: {result['updated_entries']}건")

    if result['errors']:
        print("\n⚠️  오류:")
        for error in result['errors']:
            print(f"  - {error}")

    # 재학습 트리거 확인
    if manager.check_retrain_trigger():
        print("\n📊 재학습 권장: 신규 데이터 50건 이상 누적")

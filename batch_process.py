#!/usr/bin/env python3
"""
배치 처리 스크립트

모든 카드의 XLS 파일을 일괄 처리
"""
import subprocess
from pathlib import Path
import pandas as pd
from datetime import datetime


def find_all_xls_files(input_dir="input"):
    """
    모든 XLS 파일 찾기

    Returns:
        {
            카드번호: [파일경로 리스트]
        }
    """
    input_path = Path(input_dir)
    card_files = {}

    for card_dir in input_path.iterdir():
        if card_dir.is_dir():
            card_number = card_dir.name
            files = list(card_dir.glob("*.xls*"))

            if files:
                card_files[card_number] = sorted(files)

    return card_files


def process_single_file(file_path, card_number):
    """
    단일 파일 처리

    Args:
        file_path: 입력 파일 경로
        card_number: 카드번호

    Returns:
        처리 결과 딕셔너리
    """
    print(f"\n{'='*60}")
    print(f"처리 중: {file_path.name} (카드: {card_number})")
    print(f"{'='*60}")

    try:
        # 1단계: 분류 실행
        output_name = f"{card_number}_{file_path.stem}"
        classify_output = f"output/temp/{output_name}_분류.csv"

        cmd_classify = [
            "python3", "main.py", "classify",
            "--input", str(file_path),
            "--output", classify_output,
            "--claude",
            "--card", card_number
        ]

        result = subprocess.run(
            cmd_classify,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            print(f"❌ 분류 실패: {result.stderr}")
            return {
                "file": file_path.name,
                "card": card_number,
                "status": "분류 실패",
                "error": result.stderr[:200]
            }

        # 2단계: 최종 확정
        cmd_finalize = [
            "python3", "main.py", "finalize",
            "--input", classify_output,
            "--card", card_number
        ]

        result = subprocess.run(
            cmd_finalize,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            print(f"❌ 최종 확정 실패: {result.stderr}")
            return {
                "file": file_path.name,
                "card": card_number,
                "status": "확정 실패",
                "error": result.stderr[:200]
            }

        print(f"✅ 완료")

        return {
            "file": file_path.name,
            "card": card_number,
            "status": "성공",
            "error": None
        }

    except subprocess.TimeoutExpired:
        return {
            "file": file_path.name,
            "card": card_number,
            "status": "타임아웃",
            "error": "300초 초과"
        }
    except Exception as e:
        return {
            "file": file_path.name,
            "card": card_number,
            "status": "오류",
            "error": str(e)
        }


def batch_process_all():
    """모든 카드 일괄 처리"""
    print("="*60)
    print("법인카드 일괄 분류 시작")
    print("="*60)

    # temp 디렉토리 생성
    Path("output/temp").mkdir(parents=True, exist_ok=True)

    # 모든 파일 찾기
    card_files = find_all_xls_files()

    print(f"\n발견된 카드: {len(card_files)}개")
    print(f"총 파일 수: {sum(len(files) for files in card_files.values())}개\n")

    # 카드별 파일 목록 출력
    for card, files in card_files.items():
        print(f"  {card}: {len(files)}개 파일")

    print("\n처리 시작...")

    # 처리 결과 수집
    results = []

    # 카드별로 처리
    for card_number, files in sorted(card_files.items()):
        for file_path in files:
            result = process_single_file(file_path, card_number)
            results.append(result)

    # 결과 요약
    print("\n" + "="*60)
    print("일괄 처리 완료")
    print("="*60)

    # 통계
    success_count = sum(1 for r in results if r['status'] == '성공')
    fail_count = len(results) - success_count

    print(f"\n총 처리: {len(results)}개 파일")
    print(f"성공: {success_count}개")
    print(f"실패: {fail_count}개")

    if fail_count > 0:
        print("\n[실패 목록]")
        for r in results:
            if r['status'] != '성공':
                print(f"  - {r['card']}/{r['file']}: {r['status']}")

    # 결과 로그 저장
    results_df = pd.DataFrame(results)
    results_df.to_csv(
        f"output/배치처리_결과_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # 생성된 최종 파일 목록
    print("\n[생성된 최종 파일]")
    final_files = sorted(Path("output").glob("법인카드_*.csv"))
    for f in final_files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.name} ({size_kb:.1f}KB)")

    print(f"\n✅ 배치 처리 완료!")


if __name__ == "__main__":
    batch_process_all()

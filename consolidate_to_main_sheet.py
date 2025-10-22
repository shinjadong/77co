#!/usr/bin/env python3
"""
메인 시트 통합 스크립트

모든 카드 데이터를 처리하여 칠칠기업_법인카드.xlsx 양식에 맞게 통합
"""
import pandas as pd
import openpyxl
from pathlib import Path
from datetime import datetime
import subprocess


def find_input_files():
    """Input 폴더에서 모든 파일 찾기"""
    input_dir = Path("input")

    if not input_dir.exists():
        print("❌ input 폴더가 없습니다")
        return {}

    files = {}

    # 모든 XLS/XLSX 파일 찾기
    for file_path in input_dir.glob("*승인일자*"):
        if file_path.suffix in ['.xls', '.xlsx']:
            # 파일명에서 카드번호 추출
            # 예: 3987_7월_승인일자.xlsx → 3987
            # 예: 6974(9904)_7월_승인일자.xlsx → 6974
            filename = file_path.stem

            # 카드번호 추출
            card_number = filename.split('_')[0].split('(')[0]

            if card_number not in files:
                files[card_number] = []

            files[card_number].append(file_path)

    return files


def process_card_files(card_number, file_paths):
    """
    카드의 모든 파일 처리 및 통합

    Args:
        card_number: 카드번호
        file_paths: 파일 경로 리스트

    Returns:
        통합된 DataFrame
    """
    all_results = []

    for file_path in sorted(file_paths):
        print(f"\n  처리: {file_path.name}")

        try:
            # 1. 분류 실행
            temp_output = f"output/temp/{card_number}_{file_path.stem}_분류.csv"

            cmd = [
                "python3", "main.py", "classify",
                "--input", str(file_path),
                "--output", temp_output,
                "--claude",
                "--card", card_number
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                check=True
            )

            # 2. 최종 확정
            cmd_finalize = [
                "python3", "main.py", "finalize",
                "--input", temp_output,
                "--card", card_number
            ]

            result = subprocess.run(
                cmd_finalize,
                capture_output=True,
                text=True,
                timeout=300,
                check=True
            )

            # 3. 결과 파일 찾기
            # output/법인카드_(월)월_{카드}.csv 형식
            result_files = list(Path("output").glob(f"법인카드_*월_{card_number}.csv"))

            if result_files:
                latest_file = max(result_files, key=lambda x: x.stat().st_mtime)
                df = pd.read_csv(latest_file, encoding='utf-8-sig')

                # 승인일자를 결제일자로 컬럼명 변경 (메인 시트 양식 맞추기)
                if '승인일자' in df.columns:
                    df = df.rename(columns={'승인일자': '결제일자'})

                all_results.append(df)
                print(f"    ✅ {len(df)}건 처리")

        except subprocess.TimeoutExpired:
            print(f"    ⏱ 타임아웃: {file_path.name}")
        except Exception as e:
            print(f"    ❌ 오류: {str(e)[:100]}")

    # 모든 결과 통합
    if all_results:
        combined = pd.concat(all_results, ignore_index=True)

        # 날짜 정렬
        combined['결제일자'] = pd.to_datetime(combined['결제일자'], errors='coerce')
        combined = combined.sort_values('결제일자')

        # 최종 4컬럼만
        return combined[['결제일자', '가맹점명', '이용금액', '사용용도']]

    return pd.DataFrame()


def create_main_sheet(output_path="output/칠칠기업_법인카드_완성본.xlsx"):
    """
    메인 시트 생성 (카드별 시트)

    Args:
        output_path: 출력 경로
    """
    print("="*60)
    print("메인 시트 통합 작업 시작")
    print("="*60)

    # temp 디렉토리 생성
    Path("output/temp").mkdir(parents=True, exist_ok=True)

    # Input 파일 찾기
    card_files = find_input_files()

    if not card_files:
        print("\n❌ 처리할 파일이 없습니다")
        print("input 폴더에 *승인일자*.xls(x) 파일을 넣어주세요")
        return

    print(f"\n발견된 카드: {len(card_files)}개")
    for card, files in sorted(card_files.items()):
        print(f"  {card}: {len(files)}개 파일")

    # Excel Writer 생성
    writer = pd.ExcelWriter(output_path, engine='openpyxl')

    # 카드별 처리
    card_summary = {}

    for card_number in sorted(card_files.keys()):
        file_paths = card_files[card_number]

        print(f"\n{'='*60}")
        print(f"{card_number} 카드 처리 중...")
        print(f"{'='*60}")

        # 카드 데이터 통합
        card_df = process_card_files(card_number, file_paths)

        if len(card_df) > 0:
            # 시트명 결정 (메인 시트와 동일하게)
            sheet_name = card_number

            # 메인 시트에 추가
            card_df.to_excel(writer, sheet_name=sheet_name, index=False)

            # 통계
            card_summary[card_number] = {
                '거래수': len(card_df),
                '총금액': card_df['이용금액'].sum()
            }

            print(f"\n  ✅ {card_number} 시트 생성: {len(card_df)}건")
        else:
            print(f"\n  ⚠️ {card_number}: 데이터 없음")

    # 저장
    writer.close()

    # 결과 출력
    print(f"\n{'='*60}")
    print("메인 시트 생성 완료")
    print(f"{'='*60}")

    print(f"\n✅ 파일: {output_path}")
    print(f"\n[카드별 요약]")

    total_transactions = 0
    total_amount = 0

    for card, stats in sorted(card_summary.items()):
        print(f"\n{card} 시트:")
        print(f"  거래: {stats['거래수']}건")
        print(f"  금액: {stats['총금액']:,}원")

        total_transactions += stats['거래수']
        total_amount += stats['총금액']

    print(f"\n{'='*60}")
    print(f"전체 합계: {total_transactions}건, {total_amount:,}원")
    print(f"{'='*60}")


if __name__ == "__main__":
    create_main_sheet()

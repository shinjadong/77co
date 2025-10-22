"""
피드백 및 학습 모듈

확정 라벨 수집 및 정답 DB 자동 업데이트
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict


class FeedbackManager:
    """
    피드백 관리 및 정답 DB 업데이트 클래스
    """

    def __init__(
        self,
        master_db_path: Path,
        feedback_log_path: Path = None
    ):
        """
        Args:
            master_db_path: 정답 DB 경로
            feedback_log_path: 피드백 로그 경로
        """
        self.master_db_path = Path(master_db_path)
        self.feedback_log_path = (
            Path(feedback_log_path) if feedback_log_path
            else self.master_db_path.parent / "feedback_log.csv"
        )

    def collect_feedback(
        self,
        feedback_file: Path,
        auto_update: bool = True
    ) -> Dict:
        """
        피드백 파일에서 확정 라벨 수집

        Args:
            feedback_file: 피드백 파일 경로 (확정용도 컬럼 포함)
            auto_update: 정답 DB 자동 업데이트 여부

        Returns:
            {
                "new_entries": int,
                "updated_entries": int,
                "errors": List[str]
            }
        """
        # 피드백 파일 로드
        feedback_df = pd.read_csv(feedback_file, encoding="utf-8-sig")

        # 확정용도가 입력된 행만 추출
        confirmed = feedback_df[
            feedback_df["확정용도"].notna() &
            (feedback_df["확정용도"] != "")
        ].copy()

        if len(confirmed) == 0:
            return {
                "new_entries": 0,
                "updated_entries": 0,
                "errors": ["확정용도가 입력된 항목이 없습니다"]
            }

        # 피드백 로그 저장
        self._save_feedback_log(confirmed)

        # 정답 DB 업데이트
        if auto_update:
            result = self._update_master_db(confirmed)
            return result
        else:
            return {
                "new_entries": 0,
                "updated_entries": 0,
                "errors": []
            }

    def _save_feedback_log(self, feedback_df: pd.DataFrame):
        """
        피드백 로그 저장

        Args:
            feedback_df: 확정 라벨이 포함된 DataFrame
        """
        # 로그 컬럼 준비
        log_df = feedback_df.copy()
        log_df["피드백일시"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 기존 로그 로드 (있으면)
        if self.feedback_log_path.exists():
            existing_log = pd.read_csv(
                self.feedback_log_path,
                encoding="utf-8-sig"
            )
            log_df = pd.concat([existing_log, log_df], ignore_index=True)

        # 저장
        log_df.to_csv(
            self.feedback_log_path,
            index=False,
            encoding="utf-8-sig"
        )

        print(f"피드백 로그 저장: {self.feedback_log_path}")
        print(f"  → {len(feedback_df)}건 추가")

    def _update_master_db(self, confirmed_df: pd.DataFrame) -> Dict:
        """
        정답 DB 업데이트

        Args:
            confirmed_df: 확정 라벨 DataFrame

        Returns:
            업데이트 결과
        """
        # 현재 정답 DB 로드
        master_df = pd.read_csv(
            self.master_db_path,
            encoding="utf-8-sig"
        )

        new_entries = 0
        updated_entries = 0
        errors = []

        # 각 확정 항목 처리
        for _, row in confirmed_df.iterrows():
            merchant = row["가맹점명_원본"] if "가맹점명_원본" in row else row["가맹점명"]
            category = row["확정용도"]

            # 가맹점명 정규화 (preprocessor 사용)
            from .preprocessor import normalize_merchant
            normalized_merchant = normalize_merchant(merchant)

            # 기존 DB에 있는지 확인
            existing = master_df[master_df["가맹점명"] == normalized_merchant]

            if len(existing) > 0:
                # 이미 존재 - 업데이트
                master_df.loc[
                    master_df["가맹점명"] == normalized_merchant,
                    "사용용도"
                ] = category
                updated_entries += 1
            else:
                # 신규 추가
                new_row = pd.DataFrame({
                    "가맹점명": [normalized_merchant],
                    "사용용도": [category]
                })
                master_df = pd.concat([master_df, new_row], ignore_index=True)
                new_entries += 1

        # 중복 제거
        master_df = master_df.drop_duplicates(subset=["가맹점명"], keep="last")

        # 백업 생성
        backup_path = self.master_db_path.parent / f"master_db_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        master_df_old = pd.read_csv(self.master_db_path, encoding="utf-8-sig")
        master_df_old.to_csv(backup_path, index=False, encoding="utf-8-sig")

        # 업데이트된 DB 저장
        master_df.to_csv(
            self.master_db_path,
            index=False,
            encoding="utf-8-sig"
        )

        print(f"\n정답 DB 업데이트 완료:")
        print(f"  신규 추가: {new_entries}건")
        print(f"  기존 업데이트: {updated_entries}건")
        print(f"  백업: {backup_path}")

        return {
            "new_entries": new_entries,
            "updated_entries": updated_entries,
            "errors": errors
        }

    def check_retrain_trigger(self) -> bool:
        """
        재학습 필요 여부 판단

        조건:
        - 피드백 로그에서 신규 확정 라벨 50건 이상

        Returns:
            재학습 필요 여부
        """
        if not self.feedback_log_path.exists():
            return False

        feedback_log = pd.read_csv(
            self.feedback_log_path,
            encoding="utf-8-sig"
        )

        # 최근 재학습 이후 누적 건수
        # TODO: 재학습 이력 관리 추가
        total_feedback = len(feedback_log)

        return total_feedback >= 50

    def export_training_data(
        self,
        output_path: Path,
        train_ratio: float = 0.7
    ):
        """
        학습용 데이터셋 생성

        Args:
            output_path: 출력 경로
            train_ratio: 학습 데이터 비율
        """
        # 정답 DB 로드
        master_df = pd.read_csv(
            self.master_db_path,
            encoding="utf-8-sig"
        )

        # 셔플
        master_df = master_df.sample(frac=1, random_state=42).reset_index(drop=True)

        # Train/Test 분할
        split_idx = int(len(master_df) * train_ratio)
        train_df = master_df[:split_idx]
        test_df = master_df[split_idx:]

        # 저장
        train_path = output_path.parent / f"train_{output_path.name}"
        test_path = output_path.parent / f"test_{output_path.name}"

        train_df.to_csv(train_path, index=False, encoding="utf-8-sig")
        test_df.to_csv(test_path, index=False, encoding="utf-8-sig")

        print(f"학습 데이터 생성:")
        print(f"  Train: {len(train_df)}건 → {train_path}")
        print(f"  Test: {len(test_df)}건 → {test_path}")

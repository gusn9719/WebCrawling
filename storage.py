import json
import logging
from pathlib import Path
from typing import Set

from schema import ReviewSchema

logger = logging.getLogger(__name__)


class ReviewStorage:
    def __init__(self, category: str, output_dir: Path):
        self.path = output_dir / f"{category}_reviews.jsonl"
        self.seen_ids: Set[str] = set()
        self._load_existing()

    def _load_existing(self):
        """기존 파일에서 review_id를 읽어 중복 체크용 set을 구성한다."""
        if not self.path.exists():
            logger.info(f"[storage] 신규 파일 생성 예정: {self.path}")
            return

        count = 0
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    rid = obj.get("review_id")
                    if rid:
                        self.seen_ids.add(rid)
                        count += 1
                except json.JSONDecodeError:
                    continue

        logger.info(f"[storage] 기존 리뷰 {count}개 로드 (중복 방지용)")

    def is_seen(self, review_id: str) -> bool:
        return review_id in self.seen_ids

    def save(self, reviews: list[ReviewSchema]) -> int:
        """리뷰 리스트를 JSONL에 추가 저장한다. 저장된 건수를 반환한다."""
        if not reviews:
            return 0

        saved = 0
        with open(self.path, "a", encoding="utf-8") as f:
            for review in reviews:
                if review.review_id in self.seen_ids:
                    continue
                f.write(review.to_json() + "\n")
                self.seen_ids.add(review.review_id)
                saved += 1

        if saved:
            logger.info(f"[storage] {saved}개 저장 → {self.path}")
        return saved

    def total_saved(self) -> int:
        return len(self.seen_ids)

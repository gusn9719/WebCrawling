"""
저장 담당.

리뷰를 JSONL 에 append 하고 review_id 로 중복을 막는다.
다시 실행하면 기존 파일에서 seen_ids 를 복원해 이어서 수집한다.
"""
import json
import logging

from .config import OUTPUT_DIR
from .schema import ReviewSchema

logger = logging.getLogger(__name__)


class ReviewStorage:
    """카테고리 1개 = JSONL 파일 1개. 중복 review_id 는 저장하지 않는다."""

    def __init__(self, category: str):
        OUTPUT_DIR.mkdir(exist_ok=True)
        self.path = OUTPUT_DIR / f"{category}_reviews.jsonl"
        self.seen_ids: set[str] = set()
        self.done_products: set[str] = set()
        self._restore_state()

    def _restore_state(self) -> None:
        """
        기존 JSONL 에서 review_id(중복 방지)와 product_id(완료 상품)를 복원한다.

        리뷰는 상품 단위로 한 번에 저장되므로, 중간에 429가 나면 그 상품은
        한 줄도 안 들어간다. 따라서 파일에 product_id 가 있으면 그 상품은
        끝난 것으로 보고 다시 실행할 때 통째로 건너뛴다. API 를 다시 부르지
        않으니 끊긴 지점부터 곧장 이어진다.
        """
        if not self.path.exists():
            logger.info("[storage] 신규 파일: %s", self.path.name)
            return

        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 깨진 줄은 건너뛰고 계속
                if obj.get("review_id"):
                    self.seen_ids.add(obj["review_id"])
                if obj.get("product_id"):
                    self.done_products.add(obj["product_id"])

        logger.info(
            "[storage] 복원: 리뷰 %d개 / 완료 상품 %d개 (이어서 수집)",
            len(self.seen_ids), len(self.done_products),
        )

    def is_product_done(self, product_id: str) -> bool:
        """이미 수집 완료된 상품이면 True (재실행 시 통째로 스킵)."""
        return product_id in self.done_products

    def save(self, reviews: list[ReviewSchema]) -> int:
        """신규 리뷰만 append 하고, 실제로 저장한 개수를 반환한다."""
        if not reviews:
            return 0

        saved = 0
        with open(self.path, "a", encoding="utf-8") as f:
            for review in reviews:
                if review.review_id in self.seen_ids:
                    continue
                f.write(review.to_json_line() + "\n")
                self.seen_ids.add(review.review_id)
                saved += 1

        if saved:
            logger.info("[storage] %d개 저장 (누적 %d개)", saved, len(self.seen_ids))
        return saved

    @property
    def total_saved(self) -> int:
        return len(self.seen_ids)

"""
저장 스키마.

JSONL 한 줄 = 리뷰 한 개. 수집 단계에서는 API 원본 값을 그대로 담고,
가공·전처리는 분석 단계에서 한다(수집과 분석의 책임 분리).
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class ReviewSchema:
    platform: str            # 항상 "oliveyoung"
    product_id: str          # goodsNo — API 호출·조인 키
    review_id: str           # 리뷰 고유번호 — 중복 제거 키
    product_name: str
    brand: str
    category: str            # skincare | suncare | makeup
    price: Optional[int]     # 원 단위 정수, 없으면 None
    rating: float            # 1.0 ~ 5.0
    review_text: str
    review_date: str         # YYYY-MM-DD
    skin_type: Optional[str]      # 한글 변환값 (건성 / 복합성 …)
    skin_concern: Optional[str]   # 한글 콤마 결합 (미백, 모공 …)
    reviewer_age: Optional[str]   # API 미제공 → 항상 None
    helpful_count: int = 0
    photo_exists: bool = False
    crawled_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    raw_url: str = ""

    def to_json_line(self) -> str:
        """JSONL 한 줄로 직렬화. 한글이 깨지지 않게 ensure_ascii=False."""
        return json.dumps(self.__dict__, ensure_ascii=False)

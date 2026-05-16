"""
저장 스키마.

JSONL 한 줄이 리뷰 한 개다. 수집 단계에서는 API 원본 값을 그대로 담고,
가공이나 전처리는 분석 단계에서 따로 한다.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class ReviewSchema:
    platform: str
    product_id: str          # goodsNo
    review_id: str
    product_name: str
    brand: str
    category: str            # skincare, maskpack, cleansing, suncare
    price: Optional[int]     # 원 단위 정수, 없으면 None
    rating: float            # 1.0 ~ 5.0
    review_text: str
    review_date: str         # YYYY-MM-DD
    skin_type: Optional[str]      # 한글로 변환 (건성, 복합성 등)
    skin_concern: Optional[str]   # 한글 콤마 결합 (미백, 모공 등)
    reviewer_age: Optional[str]   # API 가 안 줘서 항상 None
    helpful_count: int = 0
    photo_exists: bool = False
    crawled_at: str = field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    raw_url: str = ""

    def to_json_line(self) -> str:
        """JSONL 한 줄로 직렬화. 한글이 깨지지 않게 ensure_ascii=False."""
        return json.dumps(self.__dict__, ensure_ascii=False)

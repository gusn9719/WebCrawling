from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class ReviewSchema:
    platform: str           # 고정값 "oliveyoung"
    product_id: str
    review_id: str
    product_name: str
    brand: str
    category: str           # "skincare" | "suncare" | "makeup"
    price: Optional[int]
    rating: float
    review_text: str
    review_date: str        # "YYYY-MM-DD"
    skin_type: Optional[str]
    skin_concern: Optional[str]
    reviewer_age: Optional[str]
    helpful_count: int = 0
    photo_exists: bool = False
    crawled_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    raw_url: str = ""

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "product_id": self.product_id,
            "review_id": self.review_id,
            "product_name": self.product_name,
            "brand": self.brand,
            "category": self.category,
            "price": self.price,
            "rating": self.rating,
            "review_text": self.review_text,
            "review_date": self.review_date,
            "skin_type": self.skin_type,
            "skin_concern": self.skin_concern,
            "reviewer_age": self.reviewer_age,
            "helpful_count": self.helpful_count,
            "photo_exists": self.photo_exists,
            "crawled_at": self.crawled_at,
            "raw_url": self.raw_url,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

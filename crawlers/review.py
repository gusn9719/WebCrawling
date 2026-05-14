import time
import random
import logging
from typing import List, Optional

import requests

from config import (
    REVIEW_API_URL,
    REVIEW_SORT_TYPES,
    REVIEW_PAGE_SIZE,
    SKIN_TYPE_MAP,
    SKIN_TROUBLE_MAP,
    SLEEP_MIN,
    SLEEP_MAX,
)
from schema import ReviewSchema

logger = logging.getLogger(__name__)

REVIEW_HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.oliveyoung.co.kr",
    "Referer": "https://www.oliveyoung.co.kr/",
}


def get_reviews(
    session: requests.Session,
    goods_no: str,
    product_name: str,
    brand: str,
    category: str,
    price: Optional[int],
    product_url: str,
    max_pages_per_sort: int,
    seen_ids: set,          # storage.seen_ids — 이미 저장된 ID (읽기 전용으로 취급)
) -> List[ReviewSchema]:
    """
    도움순 / 최신순 / 낮은 평점순으로 각각 수집해 다양성을 확보한다.
    seen_ids는 이미 DB에 저장된 ID 체크용이고, 수집된 ID 등록은 storage.save에서 한다.
    """
    # 이번 호출 내 중복 제거용 (정렬 타입이 달라도 같은 리뷰가 올 수 있음)
    local_seen = set(seen_ids)
    all_reviews: List[ReviewSchema] = []

    for sort_type, sort_label in REVIEW_SORT_TYPES:
        batch = _fetch_sorted(
            session, goods_no, product_name, brand, category, price,
            product_url, sort_type, sort_label, max_pages_per_sort, local_seen,
        )
        all_reviews.extend(batch)
        if batch:
            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    return all_reviews


def _fetch_sorted(
    session, goods_no, product_name, brand, category, price,
    product_url, sort_type, sort_label, max_pages, local_seen,
) -> List[ReviewSchema]:
    """커서 기반 페이지네이션: nextCursorId/Score/Count를 다음 요청에 전달."""
    reviews = []
    cursor: dict = {}   # 첫 요청은 커서 없이, 이후엔 이전 응답의 cursor 사용

    for page_num in range(max_pages):
        payload = {
            "goodsNumber": goods_no,
            "size": REVIEW_PAGE_SIZE,
            "sortType": sort_type,
            "reviewType": "ALL",
            **cursor,   # nextCursorId, nextCursorScore, nextCursorCount
        }
        data = _api_post(session, payload)
        if data is None:
            break

        raw_list = data.get("goodsReviewList") or []
        if not raw_list:
            logger.debug(f"[review] {goods_no}/{sort_label} #{page_num}: 소진")
            break

        new = 0
        for raw in raw_list:
            r = _parse(raw, goods_no, product_name, brand, category, price, product_url)
            if r and r.review_id not in local_seen:
                local_seen.add(r.review_id)
                reviews.append(r)
                new += 1

        logger.debug(f"[review] {goods_no}/{sort_label} #{page_num}: {new}개 신규")

        if not data.get("hasNext"):
            break

        # 다음 페이지용 커서 갱신
        cursor = {
            "nextCursorId":    data.get("nextCursorId"),
            "nextCursorScore": data.get("nextCursorScore"),
            "nextCursorCount": data.get("nextCursorCount"),
        }
        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    return reviews


def _api_post(session: requests.Session, payload: dict) -> Optional[dict]:
    """API POST 후 data dict를 반환. 실패 시 None."""
    try:
        resp = session.post(REVIEW_API_URL, json=payload, headers=REVIEW_HEADERS, timeout=15)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") != "SUCCESS":
            logger.warning(f"[review] API status={body.get('status')}")
            return None
        return body.get("data") or {}
    except Exception as e:
        logger.warning(f"[review] API 실패: {e}")
        return None


def _parse(
    raw: dict,
    goods_no, product_name, brand, category, price, product_url,
) -> Optional[ReviewSchema]:
    review_id = str(raw.get("reviewId", ""))
    if not review_id:
        return None

    profile = raw.get("profileDto") or {}
    skin_type_code = profile.get("skinType")
    trouble_codes = profile.get("skinTrouble") or []

    return ReviewSchema(
        platform="oliveyoung",
        product_id=goods_no,
        review_id=review_id,
        product_name=product_name,
        brand=brand,
        category=category,
        price=price,
        rating=float(raw.get("reviewScore") or 0),
        review_text=str(raw.get("content") or "").strip(),
        review_date=str(raw.get("createdDateTime") or "").replace(".", "-")[:10],
        skin_type=SKIN_TYPE_MAP.get(skin_type_code),
        skin_concern=_join_troubles(trouble_codes),
        reviewer_age=None,   # API에 나이 필드 없음
        helpful_count=int(raw.get("recommendCount") or 0),
        photo_exists=bool(raw.get("hasPhoto")),
        raw_url=product_url,
    )


def _join_troubles(codes: list) -> Optional[str]:
    if not codes:
        return None
    return ",".join(SKIN_TROUBLE_MAP.get(c, c) for c in codes)

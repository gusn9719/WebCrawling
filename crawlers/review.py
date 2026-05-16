"""
리뷰 크롤러.

상품 dict 를 받아 모바일 리뷰 API 를 POST 호출하고 ReviewSchema
리스트를 돌려준다. Selenium 없이 requests 만 쓰므로 빠르다.

정렬 타입 5종을 모두 돌려 합치고 review_id 로 중복을 제거한다.
429(rate limit) 는 재시도해도 소용없으므로 RateLimitError 를 던져
크롤링 전체를 즉시 멈춘다(이어받기로 나중에 재개).
"""
import time
import random
import logging
from typing import Optional

import requests

from config import (
    REVIEW_API_URL,
    REVIEW_STATS_URL,
    REVIEW_HEADERS,
    REVIEW_PAGE_SIZE,
    REVIEW_REVIEW_TYPE,
    SORT_TYPES,
    MAX_PAGES_PER_SORT,
    MAX_RETRIES,
    BACKOFF_BASE_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    SLEEP_MIN_SECONDS,
    SLEEP_MAX_SECONDS,
)
from schema import ReviewSchema

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """API 가 429 를 반환했을 때. main 에서 잡아 전체 크롤링을 중단한다."""


# API 코드를 사람이 읽을 수 있는 한글로 바꾼다.
_SKIN_TYPE = {
    "A01": "건성", "A02": "복합성", "A03": "지성",
    "A04": "민감성", "A05": "중성",
}
_SKIN_CONCERN = {
    "C01": "미백", "C02": "주름", "C03": "모공", "C04": "트러블",
    "C05": "보습", "C06": "각질", "C07": "탄력", "C08": "홍조",
}


class ReviewCrawler:
    """모바일 리뷰 API 호출 + 응답 파싱을 담당한다."""

    def __init__(self, session: requests.Session):
        self._session = session

    def review_count(self, goods_no: str) -> int:
        """
        상품 통계 API 로 총 리뷰 수만 싸게 조회한다(품질 게이트용).
        조회에 실패하면 0 을 반환한다. 그러면 게이트에서 안전하게 스킵된다.
        """
        try:
            resp = self._session.get(
                REVIEW_STATS_URL.format(goods_no=goods_no),
                headers=REVIEW_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            return int(data.get("reviewCount") or 0)
        except Exception as e:
            logger.warning("  리뷰 수 조회 실패(%s): %s", goods_no, e)
            return 0

    def fetch_all(self, product: dict, seen_ids: set[str]) -> list[ReviewSchema]:
        """
        한 상품의 리뷰를 정렬 타입 5종으로 모아 중복 제거 후 반환한다.

        seen_ids: 이미 저장된 review_id (재시작 안전용). 원본은 수정하지 않는다.
        429 발생 시 RateLimitError 를 그대로 위로 던진다.
        """
        collected: list[ReviewSchema] = []
        local_seen = set(seen_ids)  # 정렬 타입 간 중복까지 이 안에서 걸러낸다

        for sort_type in SORT_TYPES:
            before = len(collected)
            self._collect_one_sort(product, sort_type, local_seen, collected)
            logger.info(
                "  └ [%s] +%d개", sort_type, len(collected) - before
            )

        return collected

    def _collect_one_sort(
        self,
        product: dict,
        sort_type: str,
        local_seen: set[str],
        collected: list[ReviewSchema],
    ) -> None:
        """
        한 정렬 타입을 커서로 끝까지 넘기며 새 리뷰를 collected 에 채운다.

        이 API 는 page 번호가 아니라 커서 방식이다. 직전 응답의
        nextCursorId/Score/Count 를 다음 요청의 cursorId/Score/Count 로
        넘긴다. 첫 요청은 셋 다 None 으로 보낸다. 보통 정렬당 100개쯤에서
        hasNext 가 False 가 되며 멈춘다.
        """
        cursor_id = cursor_score = cursor_count = None

        for _ in range(MAX_PAGES_PER_SORT):
            data = self._request_page(
                product["goods_no"], sort_type,
                cursor_id, cursor_score, cursor_count,
            )
            raw_list = data.get("goodsReviewList") or []
            if not raw_list:
                break

            new_on_page = 0
            for raw in raw_list:
                review = self._parse(raw, product)
                if review and review.review_id not in local_seen:
                    local_seen.add(review.review_id)
                    collected.append(review)
                    new_on_page += 1

            if not data.get("hasNext"):
                break

            # 안전장치: 커서가 안 움직여 같은 페이지가 반복되면 중단
            if new_on_page == 0:
                break

            cursor_id = data.get("nextCursorId")
            cursor_score = data.get("nextCursorScore")
            cursor_count = data.get("nextCursorCount")
            time.sleep(random.uniform(SLEEP_MIN_SECONDS, SLEEP_MAX_SECONDS))

    def _request_page(
        self,
        goods_no: str,
        sort_type: str,
        cursor_id,
        cursor_score,
        cursor_count,
    ) -> dict:
        """
        커서 1회분 리뷰를 가져온다. 일시적 오류는 지수 백오프로 최대 3회 재시도.
        429 는 RateLimitError 로 즉시 중단, 그 외 실패는 빈 dict 반환(해당 정렬 종료).
        """
        payload = {
            "goodsNumber": goods_no,
            "size": REVIEW_PAGE_SIZE,
            "sortType": sort_type,
            "reviewType": REVIEW_REVIEW_TYPE,
            "cursorId": cursor_id,
            "cursorScore": cursor_score,
            "cursorCount": cursor_count,
        }

        for attempt in range(MAX_RETRIES + 1):  # 최초 1회 + 재시도 MAX_RETRIES회
            try:
                resp = self._session.post(
                    REVIEW_API_URL,
                    json=payload,
                    headers=REVIEW_HEADERS,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                if resp.status_code == 429:
                    raise RateLimitError(
                        f"API 429 (rate limit), goods_no={goods_no}"
                    )
                resp.raise_for_status()

                body = resp.json()
                if body.get("status") != "SUCCESS":
                    logger.warning("  리뷰 API 오류 응답: %s", body.get("message"))
                    return {}
                return body.get("data") or {}

            except RateLimitError:
                raise  # 재시도하지 않고 위로 던져 전체를 멈춘다
            except Exception as e:
                if attempt == MAX_RETRIES:
                    logger.warning("  리뷰 API 재시도 초과, 이 정렬 건너뜀: %s", e)
                    return {}
                wait = BACKOFF_BASE_SECONDS * (2 ** attempt)  # 1s, 2s, 4s
                logger.warning(
                    "  리뷰 API 실패(%s), %ds 후 재시도 (%d/%d)",
                    e, wait, attempt + 1, MAX_RETRIES,
                )
                time.sleep(wait)

        return {}

    @staticmethod
    def _parse(raw: dict, product: dict) -> Optional[ReviewSchema]:
        """API 응답 한 건을 ReviewSchema 로 변환. review_id 없으면 None."""
        review_id = str(raw.get("reviewId") or "")
        if not review_id:
            return None

        profile = raw.get("profileDto") or {}
        concern_codes = profile.get("skinTrouble") or []
        concern = ", ".join(
            _SKIN_CONCERN.get(code, code) for code in concern_codes
        )

        return ReviewSchema(
            platform="oliveyoung",
            product_id=product["goods_no"],
            review_id=review_id,
            product_name=product["name"],
            brand=product["brand"],
            category=product["category"],
            price=product["price"],
            rating=float(raw.get("reviewScore") or 0),
            review_text=str(raw.get("content") or "").strip(),
            review_date=str(raw.get("createdDateTime") or "").replace(".", "-")[:10],
            skin_type=_SKIN_TYPE.get(profile.get("skinType")),
            skin_concern=concern or None,
            reviewer_age=None,  # API 응답에 나이 필드 없음
            helpful_count=int(raw.get("recommendCount") or 0),
            photo_exists=bool(raw.get("hasPhoto")),
            raw_url=product["url"],
        )

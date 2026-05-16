"""
올리브영 리뷰 크롤러 — 진입점.

이 파일은 오케스트레이션만 한다. 실제 로직은 각 모듈이 가진다.
흐름:

    (선택) 로그인 → 판매랭킹에서 상품 URL 수집 → 리뷰 수 품질 게이트 →
    상품 메타데이터 → 리뷰 API(커서) 수집 → JSONL 저장
    (중단/재시작 시 완료 상품은 건너뛰고 이어서 수집)

실행:
    python main.py --category all --max-products 100 --no-login

로그인은 선택이다. 비로그인도 커서 페이지네이션으로 정렬 타입당 ~100개
(상품당 300+)를 수집한다. 로그인 시 정렬당 100개 이상도 가능하지만,
대량 수집 시 rate limit 위험이 커지므로 무인 실행은 --no-login 권장.
"""
import argparse
import logging
import random
import sys
import time

import requests
from tqdm import tqdm

from browser import OliveYoungBrowser
from auth import OliveYoungAuth
from storage import ReviewStorage
from crawlers.category import CategoryCrawler
from crawlers.product import ProductCrawler
from crawlers.review import ReviewCrawler, RateLimitError
from config import (
    CATEGORIES,
    DEFAULT_MAX_PRODUCTS,
    MIN_REVIEW_COUNT,
    LOG_FILE,
    USER_AGENT,
    SLEEP_MIN_SECONDS,
    SLEEP_MAX_SECONDS,
)

logger = logging.getLogger(__name__)


def main() -> None:
    args = _parse_args()
    categories = CATEGORIES if args.category == "all" else [args.category]

    browser = OliveYoungBrowser(headless=False)
    browser.start()
    session = _build_session()

    # 로그인은 선택: 비로그인도 정렬당 ~100개(상품당 300+) 수집된다.
    # --no-login: 무인(밤샘) 실행용 — 로그인/수동 프롬프트를 건너뛰어
    # input() 에서 멈추지 않게 한다.
    if args.no_login:
        logger.info("--no-login: 비로그인 진행 (무인 안전, 정렬당 ~100개)")
    else:
        auth = OliveYoungAuth(browser, session)
        if auth.login():
            logger.info("세션 정상 → 정렬당 100개+ 수집 가능")
        else:
            logger.info("비로그인 진행 → 정렬당 ~100개 (상품당 300+ 목표 달성 가능)")

    category_crawler = CategoryCrawler(browser)
    product_crawler = ProductCrawler(browser)
    review_crawler = ReviewCrawler(session)

    try:
        for category in categories:
            _crawl_category(
                category,
                args.max_products,
                category_crawler,
                product_crawler,
                review_crawler,
            )
    except RateLimitError as e:
        # 429 는 재시도해도 소용없으므로 즉시 멈추고 사용자에게 알린다.
        # (요청량/IP 기준으로 일시 차단되며, 보통 수 시간 내 회복된다)
        logger.error("rate limit 감지 — 크롤링 중단: %s", e)
        print("\n[중단] API rate limit(429)에 걸렸습니다.")
        print("       잠시(보통 수 시간) 후 같은 명령으로 다시 실행하면")
        print("       완료한 상품은 건너뛰고 멈춘 지점부터 이어서 수집합니다.")
        print("       지금까지 수집한 리뷰는 output 폴더에 안전하게 저장돼 있습니다.\n")
    finally:
        browser.quit()

    logger.info("=== 크롤링 종료 ===")


def _crawl_category(
    category: str,
    max_products: int,
    category_crawler: CategoryCrawler,
    product_crawler: ProductCrawler,
    review_crawler: ReviewCrawler,
) -> None:
    """카테고리 1개를 처음부터 끝까지 수집한다."""
    storage = ReviewStorage(category)
    logger.info(
        "=== [%s] 시작 | 목표 %d개 상품 | 기존 %d개 리뷰 ===",
        category, max_products, storage.total_saved,
    )

    product_urls = category_crawler.get_product_urls(category, max_products)
    logger.info("[%s] 상품 %d개 수집됨", category, len(product_urls))

    skipped = 0
    resumed = 0
    for url in tqdm(product_urls, desc=category):
        try:
            goods_no = ProductCrawler.goods_no_from_url(url)

            # 재실행: 이미 끝낸 상품은 API 호출 없이 즉시 스킵
            # (이게 없으면 재개 시 완료 상품을 또 긁다가 똑같이 429 남)
            if storage.is_product_done(goods_no):
                resumed += 1
                continue

            # 품질 게이트: 상세 페이지를 열기 전, 리뷰 수부터 싸게 확인
            count = review_crawler.review_count(goods_no)
            if count < MIN_REVIEW_COUNT:
                skipped += 1
                logger.info(
                    "[%s] 리뷰 %d개(<%d) 품질 게이트 스킵: %s",
                    category, count, MIN_REVIEW_COUNT, goods_no,
                )
                continue

            product = product_crawler.fetch(url, category)
            if product is None:
                continue  # 상품 단위 실패는 로그만 남기고 다음으로

            reviews = review_crawler.fetch_all(product, storage.seen_ids)
            storage.save(reviews)
        except RateLimitError:
            raise  # 전체 중단 — main 에서 처리
        except Exception as e:
            logger.error("[%s] 상품 처리 실패, skip: %s (%s)", category, url, e)

        time.sleep(random.uniform(SLEEP_MIN_SECONDS, SLEEP_MAX_SECONDS))

    logger.info(
        "=== [%s] 완료: 누적 %d개 리뷰 | 이어받기 스킵 %d개 | 품질 게이트 스킵 %d개 → %s ===",
        category, storage.total_saved, resumed, skipped, storage.path.name,
    )


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="올리브영 리뷰 크롤러")
    parser.add_argument(
        "--category",
        required=True,
        choices=CATEGORIES + ["all"],
        help="수집할 카테고리 (또는 all = 전체 순회)",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=DEFAULT_MAX_PRODUCTS,
        help=f"카테고리당 최대 상품 수 (기본 {DEFAULT_MAX_PRODUCTS}, 랭킹 천장 100)",
    )
    parser.add_argument(
        "--no-login",
        action="store_true",
        help="로그인/수동 프롬프트 건너뜀 (무인·밤샘 실행 권장)",
    )
    return parser.parse_args()


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


if __name__ == "__main__":
    _setup_logging()
    main()

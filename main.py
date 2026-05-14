import argparse
import logging
import random
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

from browser import create_driver
from config import CATEGORY_URLS, DEFAULT_HEADERS, OUTPUT_DIR, SLEEP_MIN, SLEEP_MAX
from crawlers.category import get_product_urls
from crawlers.product import get_product_info
from crawlers.review import get_reviews
from storage import ReviewStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("crawler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="올리브영 리뷰 크롤러")
    parser.add_argument(
        "--category",
        choices=list(CATEGORY_URLS.keys()),
        required=True,
        help="수집할 카테고리 (skincare | suncare | makeup)",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=100,
        help="수집할 최대 상품 수 (기본값: 100)",
    )
    parser.add_argument(
        "--max-review-pages",
        type=int,
        default=5,
        help="정렬 타입당 최대 페이지 수 (기본값: 5 → 타입 3종×50개 + 사진10개 = 상품당 최대 160개)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="헤드리스 Chrome 사용 (기본값: True)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"JSONL 저장 디렉터리 (기본값: {OUTPUT_DIR})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    storage = ReviewStorage(args.category, args.output_dir)
    logger.info(
        f"크롤링 시작 | 카테고리={args.category} | "
        f"max_products={args.max_products} | max_review_pages={args.max_review_pages}"
    )
    logger.info(f"기존 수집 리뷰: {storage.total_saved()}개 (중복 건너뜀)")

    # ── 1단계: 카테고리 페이지에서 상품 URL 수집 ──────────────────────────
    logger.info("=== 1단계: 상품 URL 수집 ===")
    driver = create_driver(headless=args.headless)
    try:
        product_urls = get_product_urls(driver, args.category, args.max_products)
    finally:
        driver.quit()

    logger.info(f"수집된 상품 URL: {len(product_urls)}개")
    if not product_urls:
        logger.error("상품 URL이 없습니다. 셀렉터를 확인하세요.")
        sys.exit(1)

    # ── 2단계: 상품 정보 + 리뷰 수집 ─────────────────────────────────────
    logger.info("=== 2단계: 상품 정보 & 리뷰 수집 ===")
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    driver = create_driver(headless=args.headless)
    _sync_cookies(driver, session)  # Selenium 쿠키 → requests 세션으로 전달
    try:
        for product_url in tqdm(product_urls, desc=f"[{args.category}] 상품"):
            try:
                _process_product(
                    driver=driver,
                    session=session,
                    product_url=product_url,
                    category=args.category,
                    max_review_pages=args.max_review_pages,
                    storage=storage,
                )
            except Exception as e:
                logger.error(f"[main] 상품 처리 중 예외 발생, 건너뜀: {product_url} | {e}")

            time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))
    finally:
        driver.quit()

    logger.info(f"크롤링 완료 | 총 저장 리뷰: {storage.total_saved()}개 → {args.output_dir}")


def _sync_cookies(driver, session: requests.Session):
    """Selenium 쿠키를 requests 세션에 복사한다 (sortType 등 API 파라미터가 제대로 동작하도록)."""
    from config import BASE_URL
    driver.get(BASE_URL)
    time.sleep(3)
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
    logger.info(f"[main] 쿠키 {len(driver.get_cookies())}개 동기화 완료")


def _process_product(
    driver,
    session: requests.Session,
    product_url: str,
    category: str,
    max_review_pages: int,
    storage: ReviewStorage,
):
    result = get_product_info(driver, product_url)
    if result is None:
        logger.warning(f"[main] 상품 정보 수집 실패, 건너뜀: {product_url}")
        return

    goods_no, product_name, brand, price = result
    logger.info(f"[main] 상품: {product_name} ({goods_no})")

    reviews = get_reviews(
        session=session,
        goods_no=goods_no,
        product_name=product_name,
        brand=brand,
        category=category,
        price=price,
        product_url=product_url,
        max_pages_per_sort=max_review_pages,
        seen_ids=storage.seen_ids,
    )

    saved = storage.save(reviews)
    logger.info(f"[main] goodsNo={goods_no}: 리뷰 {saved}개 저장")


if __name__ == "__main__":
    main()

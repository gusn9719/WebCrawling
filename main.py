"""
올리브영 리뷰 크롤러 진입점.

인자를 읽고 로깅을 켠 뒤 CrawlPipeline 에 넘긴다.
실제 수집 흐름은 oliveyoung.pipeline 에 있다.

실행:
  python main.py --category all --max-products 100
"""
import argparse
import logging
import sys

from oliveyoung.config import CATEGORIES, DEFAULT_MAX_PRODUCTS, LOG_FILE
from oliveyoung.pipeline import CrawlPipeline


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="올리브영 리뷰 크롤러")
    parser.add_argument(
        "--category",
        required=True,
        choices=CATEGORIES + ["all"],
        help="수집할 카테고리 또는 all (전체 순회)",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        default=DEFAULT_MAX_PRODUCTS,
        help=f"카테고리당 최대 상품 수 (기본 {DEFAULT_MAX_PRODUCTS}, 랭킹 천장 100)",
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
    args = _parse_args()
    categories = CATEGORIES if args.category == "all" else [args.category]
    CrawlPipeline(categories, args.max_products).run()

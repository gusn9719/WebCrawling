"""
카테고리 크롤러 (판매랭킹 기반).

책임: 카테고리 이름을 받아 판매순위 상위 상품의 상세 URL 리스트를 돌려준다.
판매랭킹 = 베스트셀러이므로 "질 좋은 상품"이 위쪽에 모인다.
랭킹 페이지는 상위 100개를 한 페이지에 주므로 페이지네이션이 필요 없다.
"""
import re
import logging

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from browser import OliveYoungBrowser
from config import ranking_url, PAGE_LOAD_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

_GOODS_LINK = "a[href*='getGoodsDetail'][href*='goodsNo=']"
_GOODS_NO_PATTERN = re.compile(r"goodsNo=([A-Za-z0-9]+)")


class CategoryCrawler:
    """Selenium 으로 판매랭킹 페이지를 열어 상위 상품 URL 을 순위대로 모은다."""

    def __init__(self, browser: OliveYoungBrowser):
        self._driver = browser.start()

    def get_product_urls(self, category: str, max_products: int) -> list[str]:
        """category 판매랭킹 상위에서 최대 max_products 개의 상품 URL 을 반환."""
        self._driver.get(ranking_url(category))
        try:
            WebDriverWait(self._driver, PAGE_LOAD_TIMEOUT_SECONDS).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, _GOODS_LINK))
            )
        except TimeoutException:
            logger.error("[category] %s 랭킹 페이지 로딩 실패", category)
            return []

        product_urls: list[str] = []
        seen_goods: set[str] = set()

        for anchor in self._driver.find_elements(By.CSS_SELECTOR, _GOODS_LINK):
            if len(product_urls) >= max_products:
                break
            href = anchor.get_attribute("href") or ""
            goods_no = self._extract_goods_no(href)
            if goods_no and goods_no not in seen_goods:
                seen_goods.add(goods_no)
                product_urls.append(href)

        logger.info("[category] %s 랭킹: 상품 %d개 확보", category, len(product_urls))
        return product_urls

    @staticmethod
    def _extract_goods_no(url: str) -> str:
        match = _GOODS_NO_PATTERN.search(url)
        return match.group(1) if match else ""

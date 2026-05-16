"""
상품 크롤러.

책임: 상품 상세 URL 을 받아 메타데이터 dict 를 돌려준다.
리뷰 수집에 필요한 goods_no 와 화면 표시용 이름/브랜드/가격만 추출한다.
DOM 클래스가 CSS module 해시라 class*= 부분 매칭으로 잡는다.
"""
import re
import logging
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from browser import OliveYoungBrowser
from config import PAGE_LOAD_TIMEOUT_SECONDS, MIN_VALID_PRICE, MAX_VALID_PRICE

logger = logging.getLogger(__name__)

_GOODS_NO_PATTERN = re.compile(r"goodsNo=([A-Za-z0-9]+)")
_TITLE_SELECTOR = "[class*='GoodsDetailInfo_title']"
_BRAND_SELECTOR = "[class*='TopUtils_btn-brand']"
_PRICE_SELECTOR = "[class*='GoodsDetailInfo_price']"


class ProductCrawler:
    """Selenium 으로 상품 상세 페이지에서 메타데이터를 읽는다."""

    def __init__(self, browser: OliveYoungBrowser):
        self._driver = browser.start()

    def fetch(self, product_url: str, category: str) -> Optional[dict]:
        """
        상품 메타데이터 dict 를 반환한다. 실패하면 None → 호출 측에서 skip.

        반환 형태:
            {goods_no, name, brand, price, category, url}
        """
        self._driver.get(product_url)
        try:
            WebDriverWait(self._driver, PAGE_LOAD_TIMEOUT_SECONDS).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, _TITLE_SELECTOR))
            )
        except TimeoutException:
            logger.warning("[product] 상세 페이지 로딩 타임아웃: %s", product_url)
            return None

        goods_no = self.goods_no_from_url(product_url)
        name = self._text(_TITLE_SELECTOR)
        if not goods_no or not name:
            logger.warning("[product] goods_no/이름 누락, skip: %s", product_url)
            return None

        return {
            "goods_no": goods_no,
            "name": name,
            "brand": self._text(_BRAND_SELECTOR),
            "price": self._price(),
            "category": category,
            "url": product_url,
        }

    # ── 내부 헬퍼 ───────────────────────────────────────────────────────────

    @staticmethod
    def goods_no_from_url(url: str) -> str:
        """URL 에서 goodsNo 추출. 상세 페이지를 열기 전 품질 게이트에도 쓰인다."""
        match = _GOODS_NO_PATTERN.search(url)
        return match.group(1) if match else ""

    def _text(self, selector: str) -> str:
        try:
            return self._driver.find_element(By.CSS_SELECTOR, selector).text.strip()
        except NoSuchElementException:
            return ""

    def _price(self) -> Optional[int]:
        """원가·할인가 등 여러 값 중 유효 범위(100~100만 원)인 첫 값을 채택."""
        try:
            elements = self._driver.find_elements(By.CSS_SELECTOR, _PRICE_SELECTOR)
        except NoSuchElementException:
            return None

        for element in elements:
            digits = re.sub(r"[^\d]", "", element.text)
            if digits:
                price = int(digits)
                if MIN_VALID_PRICE < price < MAX_VALID_PRICE:
                    return price
        return None

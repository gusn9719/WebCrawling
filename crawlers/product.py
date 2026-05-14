import re
import logging
from typing import Optional, Tuple

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logger = logging.getLogger(__name__)


def get_product_info(driver, product_url: str) -> Optional[Tuple[str, str, str, Optional[int]]]:
    """
    상품 페이지에서 (goods_no, product_name, brand, price) 를 반환한다.
    파싱 실패 시 None 반환.
    """
    driver.get(product_url)

    try:
        # CSS 모듈 해시 클래스 — class*= 로 매칭 (실제 DOM 확인 완료)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='GoodsDetailInfo_title']"))
        )
    except TimeoutException:
        logger.warning(f"[product] 로딩 타임아웃: {product_url}")
        return None

    goods_no = _extract_goods_no_from_url(product_url)
    if not goods_no:
        logger.warning(f"[product] goodsNo 파싱 실패: {product_url}")
        return None

    product_name = _get_text(driver, "[class*='GoodsDetailInfo_title']")
    brand = _get_text(driver, "[class*='TopUtils_btn-brand']")
    price = _get_price(driver)

    if not product_name:
        logger.warning(f"[product] 상품명 파싱 실패: {product_url}")
        return None

    return goods_no, product_name, brand, price


def _get_text(driver, selector: str) -> str:
    """셀렉터로 텍스트를 가져온다. 없으면 빈 문자열 반환."""
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        return el.text.strip()
    except NoSuchElementException:
        return ""


def _get_price(driver) -> Optional[int]:
    """상품 가격을 정수(원)로 반환한다. 실제 DOM 확인 완료."""
    selectors = [
        "[class*='GoodsDetailInfo_price']",
        "[class*='sell-price']",
        "[class*='price-1']",
    ]
    for sel in selectors:
        try:
            # find_elements로 전부 가져와서 직접 텍스트인 것만 확인
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                # 자식 요소 없이 텍스트만 있는 리프 노드만 사용
                own_text = driver.execute_script(
                    "return Array.from(arguments[0].childNodes)"
                    ".filter(n=>n.nodeType===3).map(n=>n.textContent).join('')",
                    el
                ).strip()
                raw = re.sub(r"[^\d]", "", own_text or el.text)
                if raw:
                    price = int(raw)
                    if 100 < price < 1_000_000:   # 100원~100만원 범위만 유효
                        return price
        except NoSuchElementException:
            continue
    return None


def _extract_goods_no_from_url(url: str) -> str:
    match = re.search(r"goodsNo=([A-Za-z0-9]+)", url)
    return match.group(1) if match else ""

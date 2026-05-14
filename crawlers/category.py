import re
import time
import random
import logging
from typing import List

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config import CATEGORY_URLS, SLEEP_MIN, SLEEP_MAX

logger = logging.getLogger(__name__)


def get_product_urls(driver, category: str, max_products: int) -> List[str]:
    """카테고리 페이지를 페이지네이션하며 상품 URL 목록을 수집한다."""
    base_url = CATEGORY_URLS[category]
    product_urls: List[str] = []
    page = 1

    while len(product_urls) < max_products:
        url = f"{base_url}&page={page}"
        logger.info(f"[category] 페이지 {page} 로딩: {url}")
        driver.get(url)

        try:
            # ul.cate_prd_list — 실제 DOM 확인 완료
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.cate_prd_list"))
            )
        except TimeoutException:
            logger.warning(f"[category] 페이지 {page}: 상품 목록 로딩 타임아웃, 중단")
            break

        # a.prd_thumb — 실제 DOM 확인 완료 (각 상품 썸네일 링크)
        items = driver.find_elements(By.CSS_SELECTOR, "ul.cate_prd_list a.prd_thumb")

        if not items:
            logger.info(f"[category] 페이지 {page}: 상품 없음, 종료")
            break

        found_on_page = 0
        seen_on_page = set()
        for item in items:
            href = item.get_attribute("href") or ""
            goods_no = _extract_goods_no(href)
            # 같은 페이지 내 중복(썸네일+텍스트 링크) 제거
            if goods_no and goods_no not in seen_on_page and href not in product_urls:
                seen_on_page.add(goods_no)
                product_urls.append(href)
                found_on_page += 1
                if len(product_urls) >= max_products:
                    break

        logger.info(f"[category] 페이지 {page}: {found_on_page}개 수집 (누적 {len(product_urls)}개)")

        if found_on_page == 0:
            logger.info("[category] 더 이상 새 상품 없음, 종료")
            break

        # 다음 페이지 버튼 존재 여부 확인
        if not _has_next_page(driver, page):
            logger.info("[category] 마지막 페이지 도달")
            break

        page += 1
        time.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

    return product_urls[:max_products]


def _extract_goods_no(href: str) -> str:
    """URL에서 goodsNo 파라미터 값을 추출한다."""
    match = re.search(r"goodsNo=([A-Za-z0-9]+)", href)
    return match.group(1) if match else ""


def _has_next_page(driver, current_page: int) -> bool:
    """div.pageing 안에서 현재 페이지보다 큰 번호 링크가 있으면 True."""
    try:
        # div.pageing > a 태그들 중 텍스트가 숫자인 것
        page_links = driver.find_elements(By.CSS_SELECTOR, "div.pageing a")
        for a in page_links:
            txt = a.text.strip()
            if txt.isdigit() and int(txt) > current_page:
                return True
        # "다음" 버튼 존재 여부
        next_btns = driver.find_elements(By.CSS_SELECTOR, "div.pageing a.next, div.pageing button.next")
        return any(b.is_displayed() for b in next_btns)
    except Exception:
        return False

"""
로그인 담당 (이제 선택 사항).

리뷰 API 는 커서 방식이라 **비로그인으로도 정렬 타입당 100개**까지 받을 수 있다.
즉 "정렬 5종 × 100개" 목표는 로그인 없이도 달성된다.
로그인은 정렬당 100개를 넘어 더 깊이 받고 싶을 때만 필요하다.

책임: (선택) 올리브영에 로그인하고, 브라우저 쿠키를 requests.Session 으로
복사한 뒤, 세션이 실제로 리뷰 API 를 호출할 수 있는지 가볍게 확인한다.
"""
import os
import time
import logging

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from browser import OliveYoungBrowser
from config import (
    BASE_URL,
    PAGE_LOAD_TIMEOUT_SECONDS,
    REVIEW_API_URL,
    REVIEW_HEADERS,
    REVIEW_PAGE_SIZE,
    REVIEW_REVIEW_TYPE,
    REQUEST_TIMEOUT_SECONDS,
    LOGIN_PROBE_GOODS_NO,
)

logger = logging.getLogger(__name__)


class OliveYoungAuth:
    """(선택) Selenium 로그인 → 쿠키를 Session 으로 복사 → API 호출 가능 여부 확인."""

    def __init__(self, browser: OliveYoungBrowser, session: requests.Session):
        self._driver = browser.start()
        self._session = session

    def login(self) -> bool:
        """
        로그인을 시도하고, 세션으로 리뷰 API 를 호출할 수 있는지 반환한다.
        실패해도 비로그인으로 정렬당 ~100개는 수집되므로 크롤링은 계속된다.
        """
        self._open_login_page()

        user_id = os.getenv("OY_ID", "")
        password = os.getenv("OY_PW", "")

        if user_id and password:
            self._fill_and_submit(user_id, password)
            self._copy_cookies()
            if self._session_usable():
                logger.info("[auth] 로그인 + 세션 정상 (정렬당 100개 초과도 시도 가능)")
                return True
            logger.warning("[auth] 자동 로그인 미확인 → 수동 로그인으로 전환")

        self._wait_manual_login()
        self._copy_cookies()
        if self._session_usable():
            logger.info("[auth] 세션 정상")
            return True

        logger.info(
            "[auth] 비로그인 진행 — 정렬당 최대 ~100개 수집 (목표 달성에는 충분)"
        )
        return False

    # ── 로그인 화면 조작 ────────────────────────────────────────────────────

    def _open_login_page(self) -> None:
        self._driver.get(BASE_URL)
        time.sleep(2)
        try:
            self._driver.find_element(By.XPATH, "//a[contains(text(),'로그인')]").click()
            time.sleep(2)
        except Exception:
            pass  # 이미 로그인 폼이거나 셀렉터가 다른 경우

    def _fill_and_submit(self, user_id: str, password: str) -> None:
        """아이디·비밀번호 입력 후 로그인 버튼 클릭."""
        try:
            WebDriverWait(self._driver, PAGE_LOAD_TIMEOUT_SECONDS).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input#loginId"))
            )
            self._driver.find_element(By.CSS_SELECTOR, "input#loginId").send_keys(user_id)
            self._driver.find_element(By.CSS_SELECTOR, "input#password").send_keys(password)
            time.sleep(4)  # invisible Turnstile 자동 통과 대기
            self._driver.find_element(By.CSS_SELECTOR, "button.btn-login").click()
            time.sleep(4)
        except Exception as e:
            logger.warning("[auth] 자동 로그인 입력 중 오류: %s", e)

    def _wait_manual_login(self) -> None:
        """수동 로그인 안내. 로그인 안 해도(그냥 Enter) 비로그인으로 진행 가능."""
        print("\n" + "=" * 58)
        print("  로그인하면 정렬당 100개 '이상'도 수집할 수 있습니다.")
        print("  필요 없으면 그냥 Enter (비로그인도 정렬당 ~100개 수집).")
        print("  로그인하려면 크롬 창에서 로그인 후 Enter 를 누르세요.")
        print("=" * 58 + "\n")
        input()

    # ── 쿠키 복사 & 세션 확인 ───────────────────────────────────────────────

    def _copy_cookies(self) -> None:
        """브라우저 쿠키를 requests.Session 으로 복사."""
        cookies = self._driver.get_cookies()
        for cookie in cookies:
            self._session.cookies.set(cookie["name"], cookie["value"])
        logger.info("[auth] 쿠키 %d개 복사", len(cookies))

    def _session_usable(self) -> bool:
        """리뷰 API 를 한 번 호출해 정상 응답이 오는지만 가볍게 확인한다."""
        payload = {
            "goodsNumber": LOGIN_PROBE_GOODS_NO,
            "size": REVIEW_PAGE_SIZE,
            "sortType": "USEFUL_SCORE_DESC",
            "reviewType": REVIEW_REVIEW_TYPE,
            "cursorId": None,
            "cursorScore": None,
            "cursorCount": None,
        }
        try:
            resp = self._session.post(
                REVIEW_API_URL,
                json=payload,
                headers=REVIEW_HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            return bool(data.get("goodsReviewList"))
        except Exception as e:
            logger.warning("[auth] 세션 확인 중 오류: %s", e)
            return False

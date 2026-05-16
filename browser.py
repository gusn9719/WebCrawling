"""
브라우저 수명 관리.

이 클래스의 책임은 단 하나 — Selenium 드라이버를 만들고 닫는 것.
로그인·크롤링 로직은 절대 여기 두지 않는다.
"""
import logging

import undetected_chromedriver as uc

logger = logging.getLogger(__name__)


class OliveYoungBrowser:
    """undetected-chromedriver Chrome 인스턴스의 생성·종료만 담당한다."""

    def __init__(self, headless: bool = False):
        # 로그인 폼이 headless 에서 안 잡히는 경우가 있어 기본은 창을 띄운다.
        self._headless = headless
        self.driver: uc.Chrome | None = None

    def start(self) -> uc.Chrome:
        """드라이버를 생성해 반환한다. 이미 떠 있으면 그대로 반환."""
        if self.driver is not None:
            return self.driver

        options = uc.ChromeOptions()
        if self._headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=ko-KR")

        self.driver = uc.Chrome(options=options)
        logger.info("[browser] Chrome 드라이버 시작 (headless=%s)", self._headless)
        return self.driver

    def quit(self) -> None:
        """드라이버를 안전하게 종료한다(이미 닫혔어도 예외 없이)."""
        if self.driver is None:
            return
        try:
            self.driver.quit()
        except Exception as e:
            logger.warning("[browser] 종료 중 예외 무시: %s", e)
        finally:
            self.driver = None
            logger.info("[browser] Chrome 드라이버 종료")

    def __enter__(self) -> "OliveYoungBrowser":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.quit()

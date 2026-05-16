"""
브라우저 수명 관리.

이 클래스가 하는 일은 하나뿐이다. Selenium 드라이버를 만들고 닫는다.
크롤링 로직은 여기 두지 않는다.
"""
import logging

import undetected_chromedriver as uc

logger = logging.getLogger(__name__)


class OliveYoungBrowser:
    """undetected-chromedriver Chrome 인스턴스의 생성과 종료만 담당한다."""

    def __init__(self, headless: bool = False):
        # 사이트가 headless 브라우저를 막아 랭킹/상품 페이지가 안 그려진다.
        # 그래서 기본은 창을 띄운다.
        self._headless = headless
        self.driver: uc.Chrome | None = None

    def start(self) -> uc.Chrome:
        """드라이버를 만들어 반환한다. 이미 떠 있으면 그대로 반환한다."""
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
        """드라이버를 닫는다. 이미 닫혔어도 예외를 내지 않는다."""
        if self.driver is None:
            return
        try:
            self.driver.quit()
        except Exception as e:
            logger.warning("[browser] 종료 중 예외 무시: %s", e)
        finally:
            self.driver = None
            logger.info("[browser] Chrome 드라이버 종료")

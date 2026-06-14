"""
브라우저 수명 관리.

이 클래스가 하는 일은 하나뿐이다. Selenium 드라이버를 만들고 닫는다.
크롤링 로직은 여기 두지 않는다.
"""
import logging
import os

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

        # 드라이버를 설치된 Chrome 의 메이저 버전에 맞춘다.
        # uc 의 자동 감지가 실패하면 최신 드라이버를 받아 미스매치가 난다.
        chrome_major = self._detect_chrome_major()
        kwargs = {"options": options}
        if chrome_major is not None:
            kwargs["version_main"] = chrome_major
            logger.info("[browser] Chrome 메이저 버전 감지: %d", chrome_major)

        self.driver = uc.Chrome(**kwargs)
        logger.info("[browser] Chrome 드라이버 시작 (headless=%s)", self._headless)
        return self.driver

    @staticmethod
    def _detect_chrome_major() -> int | None:
        """설치된 Chrome 의 메이저 버전을 알아낸다. 못 찾으면 None.

        우선순위: 환경변수 CHROME_MAJOR → Windows 레지스트리(BLBeacon).
        """
        env = os.getenv("CHROME_MAJOR")
        if env and env.isdigit():
            return int(env)
        try:
            import winreg  # Windows 전용
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"
            ) as key:
                version, _ = winreg.QueryValueEx(key, "version")
                return int(version.split(".")[0])
        except Exception:
            return None

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

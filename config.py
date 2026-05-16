"""
크롤러 전역 설정.

코드 어디에도 매직 넘버를 두지 않기 위해, URL·딜레이·재시도 정책 등
"바꿀 수 있는 값"은 전부 여기에 상수로 모은다.
"""
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# 도메인
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "https://www.oliveyoung.co.kr"
MOBILE_URL = "https://m.oliveyoung.co.kr"

LOGIN_URL = f"{BASE_URL}/store/login/loginForm.do"
REVIEW_API_URL = f"{MOBILE_URL}/review/api/v2/reviews/cursor"

# 상품의 총 리뷰 수·평점을 한 번에 주는 통계 API (품질 게이트에 사용).
REVIEW_STATS_URL = f"{MOBILE_URL}/review/api/v2/reviews/{{goods_no}}/stats"

# ─────────────────────────────────────────────────────────────────────────────
# 상품 선정 = 판매랭킹 (베스트셀러 = 품질 프록시)
#
# getBestList.do 는 카테고리별 판매순위 상위 100개를 한 페이지에 준다.
#   dispCatNo   = 900000100100001  (판매랭킹 보드, 고정)
#   fltDispCatNo= 카테고리 코드      (아래 표, 사이트에서 검증한 값)
# 페이지네이션 불필요 — 상위 100개가 한 번에 로드된다.
# ─────────────────────────────────────────────────────────────────────────────
_RANKING_URL = f"{BASE_URL}/store/main/getBestList.do?dispCatNo=900000100100001"

CATEGORY_RANKING_FILTER: dict[str, str] = {
    "skincare":  "10000010001",  # 스킨케어
    "maskpack":  "10000010009",  # 마스크팩
    "cleansing": "10000010010",  # 클렌징
    "suncare":   "10000010011",  # 선케어
}

CATEGORIES: list[str] = list(CATEGORY_RANKING_FILTER.keys())


def ranking_url(category: str) -> str:
    """해당 카테고리의 판매랭킹 페이지 URL."""
    return f"{_RANKING_URL}&fltDispCatNo={CATEGORY_RANKING_FILTER[category]}"


# 품질 게이트: 리뷰가 이보다 적은 상품은 분석용으로 부실 → 수집 제외.
MIN_REVIEW_COUNT = 100

# ─────────────────────────────────────────────────────────────────────────────
# 리뷰 API
#
# 같은 상품이라도 정렬 타입을 바꾸면 다른 리뷰가 나온다.
# 5가지 정렬을 모두 돌려 합집합을 만든 뒤 review_id 로 중복을 제거한다.
# ─────────────────────────────────────────────────────────────────────────────
SORT_TYPES: list[str] = [
    "USEFUL_SCORE_DESC",  # 유용한순
    "DATETIME_DESC",      # 최신순
    "RECOMMENDED_DESC",   # 도움순
    "RATING_DESC",        # 평점 높은순
    "RATING_ASC",         # 평점 낮은순
]

REVIEW_PAGE_SIZE = 10           # 커서 1회 요청당 리뷰 수 (서버 권장값)

# 커서를 따라 넘길 최대 횟수(= 안전 상한).
# 이 API 는 커서 방식이라 hasNext=False 면 알아서 멈춘다.
# 비로그인은 정렬당 100개(약 10~11회)에서 hasNext=False 로 끝나므로
# 12면 "정렬당 ~100개" 목표에 충분하다. (로그인 시 더 받고 싶으면 늘릴 것)
MAX_PAGES_PER_SORT = 12
REVIEW_REVIEW_TYPE = "ALL"      # 텍스트/포토 구분 없이 전부

# 로그인 검증용: 리뷰가 아주 많아 항상 응답이 보장되는 상품의 goods_no.
LOGIN_PROBE_GOODS_NO = "A000000223625"

# Origin/Referer 가 없으면 API 가 CORS 로 막는다.
REVIEW_HEADERS = {
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}

# ─────────────────────────────────────────────────────────────────────────────
# 재시도 / 속도 조절
# ─────────────────────────────────────────────────────────────────────────────
MAX_RETRIES = 3                 # 일시적 네트워크 오류 재시도 횟수
BACKOFF_BASE_SECONDS = 1        # 지수 백오프 기준값 → 1s, 2s, 4s

REQUEST_TIMEOUT_SECONDS = 15    # requests 타임아웃
PAGE_LOAD_TIMEOUT_SECONDS = 15  # Selenium 요소 대기 타임아웃

# 상품/페이지 사이 랜덤 대기 (차단 회피)
SLEEP_MIN_SECONDS = 2.0
SLEEP_MAX_SECONDS = 4.0

# ─────────────────────────────────────────────────────────────────────────────
# HTTP / 출력
# ─────────────────────────────────────────────────────────────────────────────
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_MAX_PRODUCTS = 50

OUTPUT_DIR = Path(__file__).parent / "output"
LOG_FILE = Path(__file__).parent / "crawler.log"

# 가격 파싱 시 노이즈(0원, 적립금 등) 제거용 유효 범위
MIN_VALID_PRICE = 100
MAX_VALID_PRICE = 1_000_000

"""
크롤러 전역 설정.

매직 넘버를 코드에 흩지 않으려고 URL, 딜레이, 재시도 정책 같은
바꿀 만한 값을 전부 여기에 모아둔다.
"""
from pathlib import Path

# 도메인
BASE_URL = "https://www.oliveyoung.co.kr"
MOBILE_URL = "https://m.oliveyoung.co.kr"

REVIEW_API_URL = f"{MOBILE_URL}/review/api/v2/reviews/cursor"

# 상품의 총 리뷰 수와 평점을 한 번에 주는 통계 API. 품질 게이트에 쓴다.
REVIEW_STATS_URL = f"{MOBILE_URL}/review/api/v2/reviews/{{goods_no}}/stats"

# 상품 선정은 판매랭킹에서 한다. 잘 팔리는 상품이 위에 모이므로
# 분석할 만한 상품을 자연스럽게 고를 수 있다.
# getBestList.do 는 dispCatNo(판매랭킹 보드, 고정) + fltDispCatNo(카테고리)
# 조합으로 카테고리별 상위 100개를 한 페이지에 준다. 페이지네이션은 없다.
_RANKING_URL = f"{BASE_URL}/store/main/getBestList.do?dispCatNo=900000100100001"

CATEGORY_RANKING_FILTER: dict[str, str] = {
    "skincare":  "10000010001",
    "maskpack":  "10000010009",
    "cleansing": "10000010010",
    "suncare":   "10000010011",
}

CATEGORIES: list[str] = list(CATEGORY_RANKING_FILTER.keys())


def ranking_url(category: str) -> str:
    """해당 카테고리의 판매랭킹 페이지 URL."""
    return f"{_RANKING_URL}&fltDispCatNo={CATEGORY_RANKING_FILTER[category]}"


# 리뷰가 이보다 적은 상품은 분석용으로 부실하므로 수집에서 뺀다.
MIN_REVIEW_COUNT = 100

# 리뷰 API. 정렬을 바꾸면 다른 리뷰가 나오므로 5종을 모두 돌려
# 합친 뒤 review_id 로 중복을 제거한다.
SORT_TYPES: list[str] = [
    "USEFUL_SCORE_DESC",  # 유용한순
    "DATETIME_DESC",      # 최신순
    "RECOMMENDED_DESC",   # 도움순
    "RATING_DESC",        # 평점 높은순
    "RATING_ASC",         # 평점 낮은순
]

REVIEW_PAGE_SIZE = 10  # 커서 1회 요청당 리뷰 수 (서버 권장값)

# 커서를 따라 넘길 최대 횟수. 안전 상한일 뿐이고, 보통은
# hasNext=False 가 되면 정렬당 100개쯤에서 알아서 멈춘다.
MAX_PAGES_PER_SORT = 12
REVIEW_REVIEW_TYPE = "ALL"  # 텍스트/포토 구분 없이 전부

# Origin/Referer 가 없으면 API 가 CORS 로 막는다.
REVIEW_HEADERS = {
    "Content-Type": "application/json",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
}

# 재시도 / 속도 조절
MAX_RETRIES = 3             # 일시적 네트워크 오류 재시도 횟수
BACKOFF_BASE_SECONDS = 1    # 지수 백오프 기준값 (1s, 2s, 4s)

REQUEST_TIMEOUT_SECONDS = 15    # requests 타임아웃
PAGE_LOAD_TIMEOUT_SECONDS = 15  # Selenium 요소 대기 타임아웃

# 상품/페이지 사이 랜덤 대기 (차단 회피)
SLEEP_MIN_SECONDS = 2.0
SLEEP_MAX_SECONDS = 4.0

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_MAX_PRODUCTS = 50

# 이 파일은 oliveyoung/ 안에 있으므로 한 단계 위(레포 루트)에 출력한다.
_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = _ROOT / "output"
LOG_FILE = _ROOT / "crawler.log"

# 가격 파싱 시 노이즈(0원, 적립금 등)를 거르는 유효 범위
MIN_VALID_PRICE = 100
MAX_VALID_PRICE = 1_000_000

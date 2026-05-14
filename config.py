from pathlib import Path

BASE_URL = "https://www.oliveyoung.co.kr"
MOBILE_API_BASE = "https://m.oliveyoung.co.kr"

# 카테고리 페이지 URL (dispCatNo 실제 DOM 확인 완료)
CATEGORY_URLS = {
    "skincare": f"{BASE_URL}/store/display/getMCategoryList.do?dispCatNo=100000100010010",
    "suncare":  f"{BASE_URL}/store/display/getMCategoryList.do?dispCatNo=100000100010017",
    "makeup":   f"{BASE_URL}/store/display/getMCategoryList.do?dispCatNo=100000100020",
}

PRODUCT_URL_TEMPLATE = f"{BASE_URL}/store/goods/getGoodsDetail.do?goodsNo={{goods_no}}"

# 리뷰 API — 모바일 서브도메인 사용 (네트워크 캡처로 확인 완료)
REVIEW_API_URL      = f"{MOBILE_API_BASE}/review/api/v2/reviews/cursor"
REVIEW_PHOTO_API_URL = f"{MOBILE_API_BASE}/review/api/v2/reviews/photo-reviews"

# 확인된 유효 sortType (비로그인 기준)
# USEFUL_SCORE_DESC만 동작 확인. 비로그인 시 API는 상품당 최대 10개만 반환 (hasNext=False)
# 로그인 시 더 많은 페이지 수집 가능 — 추후 개선 여지
REVIEW_SORT_TYPES = [
    ("USEFUL_SCORE_DESC", "helpful"),    # 도움순 — 확인된 유일한 유효 sortType
]
REVIEW_PAGE_SIZE = 10   # API 한 페이지당 리뷰 수 (비로그인 한계)

# 피부타입 코드 매핑 (profileDto.skinType)
SKIN_TYPE_MAP = {
    "A01": "건성", "A02": "복합성", "A03": "지성",
    "A04": "민감성", "A05": "중성",
}

# 피부고민 코드 매핑 (profileDto.skinTrouble — 복수 가능)
SKIN_TROUBLE_MAP = {
    "C01": "미백", "C02": "주름", "C03": "모공", "C04": "트러블",
    "C05": "보습", "C06": "각질", "C07": "탄력", "C08": "홍조",
}

# 요청 간 딜레이 (초)
SLEEP_MIN = 1.5
SLEEP_MAX = 3.0

# User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# 기본 요청 헤더
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": BASE_URL,
}

# 출력 디렉터리
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

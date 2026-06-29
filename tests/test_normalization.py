"""
normalize_skin_type / normalize_skin_concern 단위 테스트.

실행:
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe tests/test_normalization.py
    또는
    C:\\Users\\user\\anaconda3\\envs\\oliveyoung\\python.exe -m pytest tests/test_normalization.py -v
"""
import math
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from recommendation.normalization import normalize_skin_type, normalize_skin_concern


class TestNormalizeSkinType(unittest.TestCase):

    # ── 필수 케이스 ─────────────────────────────────────────────────────────

    def test_required_full_complex(self):
        r = normalize_skin_type("복합성 · 진정/보습 · 모공 · 여드름")
        self.assertEqual(r["base_skin_type"], "복합성")
        self.assertEqual(r["skin_type_tags"], ["복합성"])
        self.assertEqual(r["skin_need_tags"], ["진정", "보습", "모공", "트러블"])
        self.assertEqual(r["skin_type_normalization_status"], "ok")

    def test_required_base_only(self):
        r = normalize_skin_type("민감성")
        self.assertEqual(r["base_skin_type"], "민감성")
        self.assertEqual(r["skin_type_tags"], ["민감성"])
        self.assertEqual(r["skin_need_tags"], [])
        self.assertEqual(r["skin_type_normalization_status"], "ok")

    def test_required_no_base_type(self):
        r = normalize_skin_type("진정/보습")
        self.assertIsNone(r["base_skin_type"])
        self.assertEqual(r["skin_type_tags"], [])
        self.assertEqual(r["skin_need_tags"], ["진정", "보습"])
        self.assertEqual(r["skin_type_normalization_status"], "no_base_skin_type")

    def test_required_none_missing(self):
        r = normalize_skin_type(None)
        self.assertIsNone(r["base_skin_type"])
        self.assertEqual(r["skin_type_tags"], [])
        self.assertEqual(r["skin_need_tags"], [])
        self.assertEqual(r["skin_type_normalization_status"], "missing")

    # ── 결측 변형 ────────────────────────────────────────────────────────────

    def test_string_nan_missing(self):
        r = normalize_skin_type("nan")
        self.assertEqual(r["skin_type_normalization_status"], "missing")

    def test_float_nan_missing(self):
        r = normalize_skin_type(float("nan"))
        self.assertEqual(r["skin_type_normalization_status"], "missing")

    def test_empty_string_missing(self):
        r = normalize_skin_type("")
        self.assertEqual(r["skin_type_normalization_status"], "missing")

    # ── 정규화 규칙 ──────────────────────────────────────────────────────────

    def test_yusumin_normalized(self):
        r = normalize_skin_type("복합성 · 유수분조절")
        self.assertEqual(r["skin_need_tags"], ["유수분 조절"])
        self.assertEqual(r["skin_type_normalization_status"], "ok")

    def test_yeodeueum_to_trouble(self):
        r = normalize_skin_type("지성 · 여드름")
        self.assertIn("트러블", r["skin_need_tags"])
        self.assertNotIn("여드름", r["skin_need_tags"])

    # ── 정규식 구분자: 공백 변형 ─────────────────────────────────────────────

    def test_separator_variants(self):
        expected_base = "복합성"
        expected_needs = ["진정", "보습"]
        cases = [
            "복합성 · 진정/보습",
            "복합성· 진정/보습",
            "복합성 ·진정/보습",
            "복합성·진정/보습",
        ]
        for case in cases:
            with self.subTest(value=case):
                r = normalize_skin_type(case)
                self.assertEqual(r["base_skin_type"], expected_base)
                self.assertEqual(r["skin_need_tags"], expected_needs)

    # ── 5가지 기본 피부 타입 ─────────────────────────────────────────────────

    def test_all_base_types(self):
        for bt in ["지성", "건성", "민감성", "복합성", "중성"]:
            with self.subTest(base=bt):
                r = normalize_skin_type(bt)
                self.assertEqual(r["base_skin_type"], bt)
                self.assertEqual(r["skin_type_normalization_status"], "ok")
                self.assertEqual(r["skin_type_tags"], [bt])

    # ── 복합 니즈 조합 ───────────────────────────────────────────────────────

    def test_complex_multi_need(self):
        r = normalize_skin_type("복합성 · 진정/보습 · 유수분조절 · 탄력")
        self.assertEqual(r["base_skin_type"], "복합성")
        self.assertEqual(r["skin_need_tags"], ["진정", "보습", "유수분 조절", "탄력"])


class TestNormalizeSkinConcern(unittest.TestCase):

    # ── 필수 케이스 ─────────────────────────────────────────────────────────

    def test_required_multi_tags(self):
        r = normalize_skin_concern("미백, 주름")
        self.assertEqual(r["skin_concern_tags"], ["미백", "주름"])
        self.assertEqual(r["skin_concern_codes"], [])
        self.assertEqual(r["skin_concern_normalization_status"], "ok")

    def test_required_trouble_and_moisture(self):
        r = normalize_skin_concern("트러블, 보습")
        self.assertEqual(r["skin_concern_tags"], ["트러블", "보습"])
        self.assertEqual(r["skin_concern_normalization_status"], "ok")

    def test_required_mixed_tag_and_code(self):
        r = normalize_skin_concern("보습, C09")
        self.assertEqual(r["skin_concern_tags"], ["보습"])
        self.assertEqual(r["skin_concern_codes"], ["C09"])
        self.assertEqual(r["skin_concern_normalization_status"], "ok")

    def test_required_code_only(self):
        r = normalize_skin_concern("C10")
        self.assertEqual(r["skin_concern_tags"], [])
        self.assertEqual(r["skin_concern_codes"], ["C10"])
        self.assertEqual(r["skin_concern_normalization_status"], "code_only")

    def test_required_none_missing(self):
        r = normalize_skin_concern(None)
        self.assertEqual(r["skin_concern_tags"], [])
        self.assertEqual(r["skin_concern_codes"], [])
        self.assertEqual(r["skin_concern_normalization_status"], "missing")

    # ── 결측 변형 ────────────────────────────────────────────────────────────

    def test_string_nan_missing(self):
        r = normalize_skin_concern("nan")
        self.assertEqual(r["skin_concern_normalization_status"], "missing")

    def test_float_nan_missing(self):
        r = normalize_skin_concern(float("nan"))
        self.assertEqual(r["skin_concern_normalization_status"], "missing")

    def test_empty_string_missing(self):
        r = normalize_skin_concern("")
        self.assertEqual(r["skin_concern_normalization_status"], "missing")

    # ── concern 내 '/' 분리 및 정규화 ────────────────────────────────────────

    def test_slash_split_in_concern(self):
        """진정/보습, C09 → tags=['진정','보습'], codes=['C09']"""
        r = normalize_skin_concern("진정/보습, C09")
        self.assertEqual(r["skin_concern_tags"], ["진정", "보습"])
        self.assertEqual(r["skin_concern_codes"], ["C09"])
        self.assertEqual(r["skin_concern_normalization_status"], "ok")

    def test_yeodeueum_in_concern(self):
        """여드름 → 트러블 정규화"""
        r = normalize_skin_concern("여드름, 보습")
        self.assertEqual(r["skin_concern_tags"], ["트러블", "보습"])
        self.assertNotIn("여드름", r["skin_concern_tags"])
        self.assertEqual(r["skin_concern_normalization_status"], "ok")

    # ── 정규식 구분자: 공백 변형 ─────────────────────────────────────────────

    def test_separator_variants(self):
        expected = ["미백", "주름"]
        cases = ["미백, 주름", "미백,주름", "미백 , 주름"]
        for case in cases:
            with self.subTest(value=case):
                r = normalize_skin_concern(case)
                self.assertEqual(r["skin_concern_tags"], expected)

    # ── 코드 ─────────────────────────────────────────────────────────────────

    def test_multiple_codes(self):
        r = normalize_skin_concern("C09, C10")
        self.assertEqual(r["skin_concern_codes"], ["C09", "C10"])
        self.assertEqual(r["skin_concern_tags"], [])
        self.assertEqual(r["skin_concern_normalization_status"], "code_only")

    def test_all_known_codes(self):
        for code in ["C09", "C10", "C11", "C12", "C13"]:
            with self.subTest(code=code):
                r = normalize_skin_concern(code)
                self.assertEqual(r["skin_concern_codes"], [code])
                self.assertEqual(r["skin_concern_tags"], [])
                self.assertEqual(r["skin_concern_normalization_status"], "code_only")

    def test_mixed_tag_code_and_slash(self):
        """보습, 진정/보습, C09 → tags=['보습','진정','보습'], codes=['C09']"""
        r = normalize_skin_concern("보습, 진정/보습, C09")
        self.assertIn("진정", r["skin_concern_tags"])
        self.assertIn("보습", r["skin_concern_tags"])
        self.assertEqual(r["skin_concern_codes"], ["C09"])
        self.assertEqual(r["skin_concern_normalization_status"], "ok")


if __name__ == "__main__":
    unittest.main(verbosity=2)

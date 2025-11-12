"""
테스트: 라우터 프로파일 v1.0
==============================

프로파일 매칭 + 앵커 스코어링 테스트
"""

import pytest
from app.rag.routing import ProfileMatcher, AnchorScorer


class TestProfileMatcher:
    """프로파일 매칭 테스트"""

    def test_dvr_nvr_query(self):
        """DVR/NVR 쿼리 → dvr_nvr 프로파일"""
        pm = ProfileMatcher()

        query = "HRD-442 교체 건"
        profiles = pm.match_profiles(query)
        assert "dvr_nvr" in profiles

    def test_video_switcher_query(self):
        """스위처 쿼리 → video_switcher 프로파일"""
        pm = ProfileMatcher()

        query = "MVS-8000 USK 설정"
        profiles = pm.match_profiles(query)
        assert "video_switcher" in profiles

    def test_intercom_query(self):
        """인터컴 쿼리 → intercom 프로파일"""
        pm = ProfileMatcher()

        query = "RTS ODIN 키패널 증설"
        profiles = pm.match_profiles(query)
        assert "intercom" in profiles

    def test_camera_query(self):
        """카메라 쿼리 → camera 프로파일"""
        pm = ProfileMatcher()

        query = "HDC-4300 렌즈 교체"
        profiles = pm.match_profiles(query)
        assert "camera" in profiles

    def test_audio_query(self):
        """오디오 쿼리 → audio 프로파일"""
        pm = ProfileMatcher()

        query = "DME-7000 Dante 설정"
        profiles = pm.match_profiles(query)
        assert "audio" in profiles

    def test_multi_profile_query(self):
        """복수 프로파일 쿼리"""
        pm = ProfileMatcher()

        # DVR + 카메라 혼재
        query = "DVR과 HDC 카메라 연동"
        profiles = pm.match_profiles(query)
        assert "dvr_nvr" in profiles or "camera" in profiles

    def test_text_normalization(self):
        """텍스트 정규화"""
        pm = ProfileMatcher()

        # 전각 하이픈
        text = "HRD－442"  # 전각 하이픈
        normalized = pm.normalize_text(text)
        assert "HRD-442" in normalized  # 표준 하이픈으로 변환

    def test_singleton_pattern(self):
        """싱글톤 패턴"""
        from app.rag.routing import get_profile_matcher

        pm1 = get_profile_matcher()
        pm2 = get_profile_matcher()
        assert pm1 is pm2


class TestAnchorScorer:
    """앵커 스코어링 테스트"""

    def test_allow_filter_pass(self):
        """allow 필터 통과"""
        scorer = AnchorScorer()

        text = "HRD-442 DVR 장비 교체 건"
        result = scorer.score_document(text, "dvr_nvr")

        assert result is not None
        assert result["pass"] is True
        assert len(result["details"]["allow_matched"]) > 0

    def test_allow_filter_fail(self):
        """allow 필터 실패"""
        scorer = AnchorScorer()

        # DVR 키워드 없는 텍스트
        text = "일반 회의록 작성 건"
        result = scorer.score_document(text, "dvr_nvr")

        assert result is not None
        assert result["pass"] is False
        assert result["details"]["reason"] == "allow_filter_failed"

    def test_deny_penalty(self):
        """deny 패널티 적용"""
        scorer = AnchorScorer()

        # DVR 키워드 + 차단 키워드 (짐벌)
        text = "DVR 장비와 짐벌 구매 건"
        result = scorer.score_document(text, "dvr_nvr")

        assert result is not None
        assert result["details"]["deny_penalty"] < 0

    def test_boost_high(self):
        """high boost 적용"""
        scorer = AnchorScorer()

        # HRD-442 (high boost)
        text = "HRD-442 교체 건"
        result = scorer.score_document(text, "dvr_nvr")

        assert result is not None
        assert result["details"]["boost_score"] >= 3.0

    def test_boost_medium(self):
        """medium boost 적용"""
        scorer = AnchorScorer()

        # DVR (medium boost)
        text = "DVR 보존용 장비 구매"
        result = scorer.score_document(text, "dvr_nvr")

        assert result is not None
        assert result["details"]["boost_score"] >= 1.5

    def test_boost_vendor(self):
        """vendor boost 적용"""
        scorer = AnchorScorer()

        # Hanwha (vendor boost)
        text = "Hanwha DVR 장비"
        result = scorer.score_document(text, "dvr_nvr")

        assert result is not None
        # vendor만으로는 pass_threshold(1.0) 미달 가능
        assert result["details"]["boost_score"] >= 1.0

    def test_proximity_bonus(self):
        """proximity 보너스 적용"""
        scorer = AnchorScorer()

        # DVR + 보존 (근접)
        text = "DVR 보존용 장비 구매 건"
        result = scorer.score_document(text, "dvr_nvr")

        assert result is not None
        assert result["details"]["proximity_bonus"] > 0

    def test_pass_threshold(self):
        """pass_threshold 체크"""
        scorer = AnchorScorer()

        # 높은 점수 (pass)
        text = "HRD-442 DVR 교체 건"
        result = scorer.score_document(text, "dvr_nvr")
        assert result["pass"] is True

        # 낮은 점수 (fail)
        text2 = "일반 장비"
        result2 = scorer.score_document(text2, "dvr_nvr")
        assert result2["pass"] is False

    def test_profile_not_found(self):
        """존재하지 않는 프로파일"""
        scorer = AnchorScorer()

        text = "test"
        result = scorer.score_document(text, "nonexistent_profile")

        assert result is None


class TestIntegrationScenarios:
    """통합 시나리오 테스트"""

    def test_scenario_dvr_replacement(self):
        """시나리오 1: DVR 장비 교체 문서"""
        pm = ProfileMatcher()
        scorer = AnchorScorer()

        query = "HRD-442 교체"
        doc_text = "HRD-442 DVR 장비 노후로 인한 교체 건. Hanwha 제품 구매 예정."

        # 프로파일 매칭
        profiles = pm.match_profiles(query)
        assert "dvr_nvr" in profiles

        # 앵커 스코어링
        result = scorer.score_document(doc_text, "dvr_nvr")
        assert result["pass"] is True
        assert result["score"] >= 3.0  # high boost + medium boost

    def test_scenario_switcher_upgrade(self):
        """시나리오 2: 스위처 증설 문서"""
        pm = ProfileMatcher()
        scorer = AnchorScorer()

        query = "MVS-8000 USK"
        doc_text = "MVS-8000 스위처 USK 증설 건. Sony 제품."

        # 프로파일 매칭
        profiles = pm.match_profiles(query)
        assert "video_switcher" in profiles

        # 앵커 스코어링
        result = scorer.score_document(doc_text, "video_switcher")
        assert result["pass"] is True

    def test_scenario_intercom_expansion(self):
        """시나리오 3: 인터컴 키패널 증설"""
        pm = ProfileMatcher()
        scorer = AnchorScorer()

        query = "ODIN 키패널"
        doc_text = "RTS ODIN 인터컴 키패널 증설 건"

        # 프로파일 매칭
        profiles = pm.match_profiles(query)
        assert "intercom" in profiles

        # 앵커 스코어링
        result = scorer.score_document(doc_text, "intercom")
        assert result["pass"] is True
        # proximity bonus (ODIN + 키패널)
        assert result["details"]["proximity_bonus"] > 0

    def test_scenario_camera_lens(self):
        """시나리오 4: 카메라 렌즈 교체"""
        pm = ProfileMatcher()
        scorer = AnchorScorer()

        query = "HDC-4300 렌즈"
        doc_text = "HDC-4300 카메라 렌즈 교체 건. Sony 제품."

        # 프로파일 매칭
        profiles = pm.match_profiles(query)
        assert "camera" in profiles

        # 앵커 스코어링
        result = scorer.score_document(doc_text, "camera")
        assert result["pass"] is True
        # proximity bonus (HDC + 렌즈)
        assert result["details"]["proximity_bonus"] > 0

    def test_scenario_audio_console(self):
        """시나리오 5: 오디오 콘솔 Dante 설정"""
        pm = ProfileMatcher()
        scorer = AnchorScorer()

        query = "DME-7000 Dante"
        doc_text = "DME-7000 오디오 콘솔 Dante 연동 설정 건"

        # 프로파일 매칭
        profiles = pm.match_profiles(query)
        assert "audio" in profiles

        # 앵커 스코어링
        result = scorer.score_document(doc_text, "audio")
        assert result["pass"] is True
        # proximity bonus (DME + Dante)
        assert result["details"]["proximity_bonus"] > 0

    def test_scenario_deny_gimbal(self):
        """시나리오 6: 차단 키워드 (짐벌) 적용"""
        scorer = AnchorScorer()

        # 짐벌 포함 문서
        doc_text = "DVR 장비와 짐벌 구매 건"

        result = scorer.score_document(doc_text, "dvr_nvr")
        assert result is not None
        # deny penalty로 점수 하락
        assert result["details"]["deny_penalty"] < 0

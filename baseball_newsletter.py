import datetime
import os
import sys
import urllib.parse
import feedparser
import pytz
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# ==========================================
# 🧪 테스트용 날짜 설정
# - 한국시리즈 2차전 날짜인 "2026-11-04"로 설정되어 있습니다.
# - 테스트 확인 후에는 None 으로 변경해 두세요!
# ==========================================
TEST_DATE = "2026-11-04"


def get_pitcher_records_from_detail(game_id, headers):
    """기본 API에 투수 정보가 없을 경우 상세 경기 API에서 승/패/세 투수를 가져옵니다."""
    detail_url = f"https://api-gw.sports.naver.com/schedule/games/{game_id}"
    try:
        res = requests.get(detail_url, headers=headers, timeout=5)
        if res.status_code == 200:
            game_data = res.json().get("result", {}).get("game", {})
            win_p = game_data.get("winnerPitcherName") or game_data.get(
                "winPitcherName"
            )
            lose_p = game_data.get("loserPitcherName") or game_data.get(
                "losePitcherName"
            )
            save_p = game_data.get("savePitcherName")
            return win_p, lose_p, save_p
    except Exception:
        pass
    return None, None, None


def get_yesterday_kbo_results(target_date_str):
    """네이버 스포츠 API를 통해 정규시즌 및 포스트시즌(한국시리즈 등) 경기 결과를 가져옵니다."""
    url = "https://api-gw.sports.naver.com/schedule/games"
    params = {
        "fields": "basic",
        "upperCategoryId": "kbaseball",
        # 중요: categoryId="kbo"를 넣으면 포스트시즌(한국시리즈)이 누락되므로 제외합니다!
        "fromDate": target_date_str,
        "toDate": target_date_str,
        "size": 50,
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"⚠️ API 호출 실패 (HTTP {response.status_code})")
            return []

        data = response.json()
        games = data.get("result", {}).get("games", [])
        results = []

        # KBO 10개 구단 이름 목록 (퓨처스리그나 국가대표 경기 제외용)
        kbo_teams = {
            "KIA",
            "삼성",
            "LG",
            "두산",
            "KT",
            "SSG",
            "롯데",
            "한화",
            "NC",
            "키움",
        }

        for g in games:
            away_team = g.get("awayTeamName", "")
            home_team = g.get("homeTeamName", "")
            category_id = g.get("categoryId", "")

            # 퓨처스(2군)

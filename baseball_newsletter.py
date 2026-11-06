import datetime
import os
import sys
import traceback
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


def safe_int(val):
    """점수 데이터가 None이거나 빈 문자열이어도 에러 없이 숫자로 변환합니다."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def get_pitcher_records_from_detail(game_id, headers):
    """기본 API에 투수 정보가 없을 경우 상세 경기 API에서 승/패/세 투수를 가져옵니다."""
    detail_url = f"https://api-gw.sports.naver.com/schedule/games/{game_id}"
    try:
        res = requests.get(detail_url, headers=headers, timeout=5)
        if res.status_code == 200:
            game_data = res.json().get("result", {}).get("game", {})
            if not game_data:
                return None, None, None
            win_p = game_data.get("winnerPitcherName") or game_data.get(
                "winPitcherName"
            )
            lose_p = game_data.get("loserPitcherName") or game_data.get(
                "losePitcherName"
            )
            save_p = game_data.get("savePitcherName")
            return win_p, lose_p, save_p
    except Exception as e:
        print(f"상세 경기 조회 참고용 로그: {e}")
    return None, None, None


def get_yesterday_kbo_results(target_date_str):
    """네이버 스포츠 API를 통해 정규시즌 및 포스트시즌(한국시리즈 등) 경기 결과를 가져옵니다."""
    url = "https://api-gw.sports.naver.com/schedule/games"
    params = {
        "fields": "basic",
        "upperCategoryId": "kbaseball",
        "fromDate": target_date_str,
        "toDate": target_date_str,
        "size": 50,
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            print(
                f"⚠️ 네이버 API 응답 코드: {response.status_code} ({response.text})"
            )
            return []

        data = response.json()
        games = data.get("result", {}).get("games", [])
        if not games:
            return []

        results = []
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
            if not isinstance(g, dict):
                continue

            away_team = g.get("awayTeamName") or ""
            home_team = g.get("homeTeamName") or ""
            category_id = str(g.get("categoryId") or "")

            # 2군(퓨처스) 경기 제외 및 KBO 10개 구단 경기만 필터링
            if "futures" in category_id.lower():
                continue
            if away_team not in kbo_teams and home_team not in kbo_teams:
                continue

            status_code = g.get("statusCode") or ""
            status_info = g.get("statusInfo") or ""
            away_score = safe_int(g.get("awayTeamScore"))
            home_score = safe_int(g.get("homeTeamScore"))

            game_title = g.get("title") or ""
            prefix = f"[{game_title}] " if game_title else ""

            # 1) 우천 취소 등 경기 취소 케이스
            if "취소" in status_info or status_code == "CANCEL":
                results.append(
                    f"- {prefix}{away_team} vs {home_team} ({status_info or '경기 취소'})"
                )
                continue

            # 2) 정상 종료된 경기 (RESULT)
            if status_code == "RESULT":
                win_p = g.get("winnerPitcherName") or g.get("winPitcherName")
                lose_p = g.get("loserPitcherName") or g.get("losePitcherName")
                save_p = g.get("savePitcherName")

                if not win_p and g.get("gameId"):
                    win_p, lose_p, save_p = get_pitcher_records_from_detail(
                        g.get("gameId"), headers
                    )

                away_records = []
                home_records = []

                if away_score > home_score:
                    if win_p:
                        away_records.append(f"승 : {win_p}")
                    if save_p:
                        away_records.append(f"세 : {save_p}")
                    if lose_p:
                        home_records.append(f"패 : {lose_p}")
                elif home_score >

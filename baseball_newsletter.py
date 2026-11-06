import datetime
import os
import sys
import urllib.parse
import feedparser
import pytz
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 테스트용 날짜 (확인 후 None 으로 변경하세요)
TEST_DATE = None

KBO_TEAM_KEYWORDS = [
    "KIA",
    "기아",
    "삼성",
    "LG",
    "두산",
    "KT",
    "SSG",
    "롯데",
    "한화",
    "NC",
    "키움",
]


def safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def is_kbo_team(name):
    if not name:
        return False
    return any(k in name for k in KBO_TEAM_KEYWORDS)


def clean_team_name(name):
    """'삼성 라이온즈' -> '삼성' 형태로 깔끔하게 정리합니다."""
    if not name:
        return ""
    return name.split()[0]


def get_pitcher_from_naver_detail(game_id, headers):
    url = f"https://api-gw.sports.naver.com/schedule/games/{game_id}"
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            g = res.json().get("result", {}).get("game", {}) or {}
            win_p = g.get("winnerPitcherName") or g.get("winPitcherName")
            lose_p = g.get("loserPitcherName") or g.get("losePitcherName")
            save_p = g.get("savePitcherName")
            return win_p, lose_p, save_p
    except Exception:
        pass
    return None, None, None


def fetch_from_naver(target_date_str):
    """1차 시도: 네이버 스포츠 API (브라우저 헤더 완벽 위장)"""
    url = "https://api-gw.sports.naver.com/schedule/games"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        ),
        "Referer": "https://m.sports.naver.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://m.sports.naver.com",
    }

    # upperCategoryId 만 조회하거나, categoryId=kbo 로 조회하는 두 가지 파라미터를 모두 시도
    param_candidates = [
        {
            "fields": "basic",
            "upperCategoryId": "kbaseball",
            "fromDate": target_date_str,
            "toDate": target_date_str,
            "size": 100,
        },
        {
            "fields": "basic",
            "upperCategoryId": "kbaseball",
            "categoryId": "kbo",
            "fromDate": target_date_str,
            "toDate": target_date_str,
            "size": 100,
        },
    ]

    for params in param_candidates:
        try:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            print(
                f"[Naver API] HTTP {res.status_code} (params: {params.get('categoryId', 'ALL')})"
            )
            if res.status_code != 200:
                continue

            games = res.json().get("result", {}).get("games", []) or []
            print(f"[Naver API] 조회된 전체 경기 수: {len(games)}")

            results = []
            for g in games:
                if not isinstance(g, dict):
                    continue
                away = clean_team_name(g.get("awayTeamName") or "")
                home = clean_team_name(g.get("homeTeamName") or "")
                cat = str(g.get("categoryId") or "").lower()

                if "futures" in cat:
                    continue
                if not (is_kbo_team(away) or is_kbo_team(home)):
                    continue

                status_code = g.get("statusCode") or ""
                status_info = g.get("statusInfo") or ""
                a_score = safe_int(g.get("awayTeamScore"))
                h_score = safe_int(g.get("homeTeamScore"))
                title = g.get("title") or ""
                prefix = f"[{title}] " if title else ""

                if "취소" in status_info or status_code == "CANCEL":
                    results.append(
                        f"- {prefix}{away} vs {home} ({status_info or '경기 취소'})"
                    )
                    continue

                if (
                    status_code == "RESULT"
                    or "종료" in status_info
                    or (a_score + h_score > 0)
                ):
                    win_p = g.get("winnerPitcherName") or g.get(
                        "winPitcherName"
                    )
                    lose_p = g.get("loserPitcherName") or g.get(
                        "losePitcherName"
                    )
                    save_p = g.get("savePitcherName")

                    if not win_p and g.get("gameId"):
                        win_p, lose_p, save_p = get_pitcher_from_naver_detail(
                            g.get("gameId"), headers
                        )

                    a_rec, h_rec = [], []
                    if a_score > h_score:
                        if win_p:
                            a_rec.append(f"승 : {win_p}")
                        if save_p:
                            a_rec.append(f"세 : {save_p}")
                        if lose_p:
                            h_rec.append(f"패 : {lose_p}")
                    elif h_score > a_score:
                        if win_p:
                            h_rec.append(f"승 : {win_p}")
                        if save_p:
                            h_rec.append(f"세 : {save_p}")
                        if lose_p:
                            a_rec.append(f"패 : {lose_p}")

                    a_str = f" ({', '.join(a_rec)})" if a_rec else ""
                    h_str = f" ({', '.join(h_rec)})" if h_rec else ""
                    results.append(
                        f"- {prefix}**{away} {a_score}**{a_str} vs **{home} {h_score}**{h_str}"
                    )
                else:
                    results.append(
                        f"- {prefix}{away} vs {home} ({status_info or '경기 예정'})"
                    )

            if results:
                return results
        except Exception as e:
            print(f"[Naver API 오류] {e}")

    return []


def fetch_from_daum(target_date_str):
    """2차 백업 시도: 다음(Daum) 스포츠 API 조회 (네이버가 해외 IP 차단 시 작동)"""
    date_compact = target_date_str.replace("-", "")
    url = "https://sports.daum.net/prx/hermes/api/game/schedule.json"
    params = {
        "page": 1,
        "leagueCode": "kbo",
        "fromDate": date_compact,
        "toDate": date_compact,
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://sports.daum.net/",
    }
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"[Daum API] HTTP {res.status_code}")
        if res.status_code != 200:
            return []

        schedule = res.json().get("schedule", {}) or {}
        games = schedule.get(date_compact, []) or []
        print(f"[Daum API] 조회된 경기 수: {len(games)}")

        results = []
        for g in games:
            away = clean_team_name(
                g.get("awayTeamName") or g.get("awayKoName") or ""
            )
            home = clean_team_name(
                g.get("homeTeamName") or g.get("homeKoName") or ""
            )
            a_score = safe_int(g.get("awayScore") or g.get("awayTeamScore"))
            h_score = safe_int(g.get("homeScore") or g.get("homeTeamScore"))
            state = str(g.get("gameStatus") or "")

            win_p = g.get("winPitcherName") or ""
            lose_p = g.get("losePitcherName") or ""
            save_p = g.get("savePitcherName") or ""

            if "CANCEL" in state.upper():
                results.append(f"- {away} vs {home} (경기 취소)")
                continue

            a_rec, h_rec = [], []
            if a_score > h_score:
                if win_p:
                    a_rec.append(f"승 : {win_p}")
                if save_p:
                    a_rec.append(f"세 : {save_p}")
                if lose_p:
                    h_rec.append(f"패 : {lose_p}")
            elif h_score > a_score:
                if win_p:
                    h_rec.append(f"승 : {win_p}")
                if save_p:
                    h_rec.append(f"세 : {save_p}")
                if lose_p:
                    a_rec.append(f"패 : {lose_p}")

            a_str = f" ({', '.join(a_rec)})" if a_rec else ""
            h_str = f" ({', '.join(h_rec)})" if h_rec else ""
            results.append(
                f"- **{away} {a_score}**{a_str} vs **{home} {h_score}**{h_str}"
            )
        return results
    except Exception as e:
        print(f"[Daum API 오류] {e}")
        return []


def fetch_from_kbo_official(target_date_str):
    """3차 백업 시도: KBO 공식 홈페이지 경기일정 API 조회"""
    date_compact = target_date_str.replace("-", "")
    url = "https://www.koreabaseball.com/ws/Main.asmx/GetKboGameList"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://www.koreabaseball.com/",
    }
    # srId: 0(정규), 1(시범), 3,4,5,7(포스트시즌 전체)
    data = {"leId": "1", "srId": "0,1,3,4,5,7,8,9", "date": date_compact}
    try:
        res = requests.post(url, data=data, headers=headers, timeout=10)
        print(f"[KBO 공식 API] HTTP {res.status_code}")
        if res.status_code != 200:
            return []

        games = res.json().get("game", []) or []
        print(f"[KBO 공식 API] 조회된 경기 수: {len(games)}")

        results = []
        for g in games:
            away = g.get("AWAY_NM") or ""
            home = g.get("HOME_NM") or ""
            a_score = safe_int(g.get("T_SCORE_CN"))
            h_score = safe_int(g.get("B_SCORE_CN"))
            cancel_id = str(g.get("CANCEL_SC_ID") or "0")

            if cancel_id != "0":
                results.append(
                    f"- {away} vs {home} ({g.get('CANCEL_SC_NM') or '경기 취소'})"
                )
                continue

            win_p = (g.get("W_PIT_P_NM") or "").strip()
            lose_p = (g.get("L_PIT_P_NM") or "").strip()
            save_p = (g.get("SV_PIT_P_NM") or "").strip()

            a_rec, h_rec = [], []
            if a_score > h_score:
                if win_p:
                    a_rec.append(f"승 : {win_p}")
                if save_p:
                    a_rec.append(f"세 : {save_p}")
                if lose_p:
                    h_rec.append(f"패 : {lose_p}")
            elif h_score > a_score:
                if win_p:
                    h_rec.append(f"승 : {win_p}")
                if save_p:
                    h_rec.append(f"세 : {save_p}")
                if lose_p:
                    a_rec.append(f"패 : {lose_p}")

            a_str = f" ({', '.join(a_rec)})" if a_rec else ""
            h_str = f" ({', '.join(h_rec)})" if h_rec else ""
            results.append(
                f"- **{away} {a_score}**{a_str} vs **{home} {h_score}**{h_str}"
            )
        return results
    except Exception as e:
        print(f"[KBO 공식 API 오류] {e}")
        return []


def get_yesterday_kbo_results(target_date_str):
    """네이버 -> KBO 공식 홈페이지 -> 다음 스포츠 순서로 경기 결과를 조회합니다."""
    results = fetch_from_naver(target_date_str)
    if results:
        return results

    print("네이버 결과 없음 -> KBO 공식 홈페이지 API 시도...")
    results = fetch_from_kbo_official(target_date_str)
    if results:
        return results

    print("KBO 공식 홈페이지 결과 없음 -> 다음 스포츠 API 시도...")
    return fetch_from_daum(target_date_str)


def get_baseball_news(max_items=5):
    try:
        q = urllib.parse.quote("KBO OR 프로야구 OR 한국시리즈")
        url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        news = []
        for entry in feed.entries[:max_items]:
            parts = entry.title.rsplit(" - ", 1)
            title = parts[0].replace("[", "(").replace("]", ")")
            press = parts[1] if len(parts) > 1 else "뉴스"
            news.append({"title": title, "press": press, "link": entry.link})
        return news
    except Exception:
        return []


def send_discord_newsletter():
    if not DISCORD_WEBHOOK_URL:
        sys.exit(1)

    kst = pytz.timezone("Asia/Seoul")
    now = datetime.datetime.now(kst)
    today_str = now.strftime("%Y년 %m월 %d일")

    if TEST_DATE:
        target_dt = datetime.datetime.strptime(TEST_DATE, "%Y-%m-%d")
    else:
        target_dt = now - datetime.timedelta(days=1)

    y_str = target_dt.strftime("%Y-%m-%d")
    y_disp = target_dt.strftime("%m월 %d일")

    games = get_yesterday_kbo_results(y_str)
    news = get_baseball_news(5)

    lines = [
        "안녕하세요 KBO 팬 여러분들! ⚾",
        f"어제({y_disp})의 경기 결과 알려드릴게요!\n",
    ]
    if games:
        lines.extend(games)
    else:
        lines.append(
            "- 어제는 진행된 KBO 공식 경기가 없었어요. (휴식일 또는 비시즌)"
        )

    lines.append("\n---\n📰 **아래는 최신 뉴스에 대한 정보들이에요!**\n")
    if news:
        for n in news:
            lines.append(f"- [{n['title']}]({n['link']}) `({n['press']})`")
    else:
        lines.append("- 오늘 아침에는 새로 올라온 뉴스가 아직 없네요.")

    lines.append("\n오늘도 활기차고 좋은 하루 보내세요! 🙌")
    desc = "\n".join(lines)[:4000]

    payload = {
        "username": "⚾ KBO 모닝 메이트",
        "embeds": [
            {
                "title": f"☀️ {today_str} KBO 아침 소식지",
                "description": desc,
                "color": 0x002B5B,
                "footer": {
                    "text": f"발송 시각: {now.strftime('%H:%M')} | 매일 아침 9시 여러분을 찾아갑니다"
                },
            }
        ],
    }

    res = requests.post(DISCORD_WEBHOOK_URL.strip(), json=payload, timeout=15)
    if res.status_code not in (200, 204):
        print(f"전송 실패: {res.status_code} {res.text}")
        sys.exit(1)
    print("발송 완료!")


if __name__ == "__main__":
    send_discord_newsletter()

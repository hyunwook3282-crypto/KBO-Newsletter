import datetime
import os
import sys
import urllib.parse
import feedparser
import pytz
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# 테스트용 날짜 (확인 후 None 으로 변경하세요)
TEST_DATE = "2026-11-04"


def safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def get_pitcher_records_from_detail(game_id, headers):
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


def get_yesterday_kbo_results(target_date_str):
    url = "https://api-gw.sports.naver.com/schedule/games"
    params = {
        "fields": "basic",
        "upperCategoryId": "kbaseball",
        "fromDate": target_date_str,
        "toDate": target_date_str,
        "size": 50,
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        if res.status_code != 200:
            return []

        games = res.json().get("result", {}).get("games", []) or []
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

            away = g.get("awayTeamName") or ""
            home = g.get("homeTeamName") or ""
            cat = str(g.get("categoryId") or "").lower()

            if "futures" in cat or (
                away not in kbo_teams and home not in kbo_teams
            ):
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

            if status_code == "RESULT":
                win_p = g.get("winnerPitcherName") or g.get("winPitcherName")
                lose_p = g.get("loserPitcherName") or g.get("losePitcherName")
                save_p = g.get("savePitcherName")

                if not win_p and g.get("gameId"):
                    win_p, lose_p, save_p = get_pitcher_records_from_detail(
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

        return results
    except Exception as e:
        print(f"경기 조회 오류: {e}")
        return []


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

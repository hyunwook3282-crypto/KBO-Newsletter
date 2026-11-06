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
# - 특정 날짜를 테스트하려면 "2026-05-05" 처럼 입력하세요.
# - 실제 매일 아침 자동 발송할 때는 None 으로 두세요!
# ==========================================
TEST_DATE = "2026-11-04"


def get_yesterday_kbo_results(target_date_str):
    """네이버 스포츠 API를 통해 특정 날짜의 KBO 경기 결과 및 투수 기록을 가져옵니다."""
    url = "https://api-gw.sports.naver.com/schedule/games"
    params = {
        # 주의: PitcherResult를 넣으면 400 에러가 발생하므로 'basic'만 사용해야 합니다.
        "fields": "basic",
        "upperCategoryId": "kbaseball",
        "categoryId": "kbo",
        "fromDate": target_date_str,
        "toDate": target_date_str,
        "size": 20,
    }
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            print(
                f"⚠️ API 호출 실패 (HTTP {response.status_code}): {response.text}"
            )
            return []

        data = response.json()
        games = data.get("result", {}).get("games", [])
        results = []

        for g in games:
            status_code = g.get("statusCode", "")
            status_info = g.get("statusInfo", "")

            away_team = g.get("awayTeamName", "원정팀")
            home_team = g.get("homeTeamName", "홈팀")
            away_score = int(g.get("awayTeamScore", 0))
            home_score = int(g.get("homeTeamScore", 0))

            # 1) 우천 취소 등 경기 취소 케이스
            if "취소" in status_info or status_code == "CANCEL":
                results.append(
                    f"- {away_team} vs {home_team} ({status_info or '경기 취소'})"
                )
                continue

            # 2) 정상 종료된 경기 (RESULT)
            if status_code == "RESULT":
                win_p = g.get("winnerPitcherName") or g.get("winPitcherName")
                lose_p = g.get("loserPitcherName") or g.get("losePitcherName")
                save_p = g.get("savePitcherName")

                away_records = []
                home_records = []

                if away_score > home_score:
                    if win_p:
                        away_records.append(f"승 : {win_p}")
                    if save_p:
                        away_records.append(f"세 : {save_p}")
                    if lose_p:
                        home_records.append(f"패 : {lose_p}")
                elif home_score > away_score:
                    if win_p:
                        home_records.append(f"승 : {win_p}")
                    if save_p:
                        home_records.append(f"세 : {save_p}")
                    if lose_p:
                        away_records.append(f"패 : {lose_p}")

                away_rec_str = (
                    f" ({', '.join(away_records)})" if away_records else ""
                )
                home_rec_str = (
                    f" ({', '.join(home_records)})" if home_records else ""
                )

                results.append(
                    f"- **{away_team} {away_score}**{away_rec_str} vs **{home_team} {home_score}**{home_rec_str}"
                )
            else:
                results.append(f"- {away_team} vs {home_team} ({status_info})")

        return results
    except Exception as e:
        print(f"⚠️ 경기 결과 조회 중 오류 발생: {e}")
        return []


def get_baseball_news(max_items=5):
    """구글 뉴스 RSS에서 최신 KBO 및 야구 뉴스를 가져옵니다."""
    query = urllib.parse.quote("KBO OR 프로야구")
    rss_url = (
        f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    )

    feed = feedparser.parse(rss_url)
    news_list = []

    for entry in feed.entries[:max_items]:
        title_parts = entry.title.rsplit(" - ", 1)
        clean_title = title_parts[0]
        press = title_parts[1] if len(title_parts) > 1 else "뉴스"

        news_list.append(
            {"title": clean_title, "press": press, "link": entry.link}
        )
    return news_list


def send_discord_newsletter():
    """친근한 대화체로 경기 결과와 오늘 뉴스를 조합해 디스코드로 전송합니다."""
    if not DISCORD_WEBHOOK_URL:
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    kst = pytz.timezone("Asia/Seoul")
    now = datetime.datetime.now(kst)
    today_str = now.strftime("%Y년 %m월 %d일")

    # TEST_DATE가 설정되어 있으면 해당 날짜로 조회, 아니면 실제 어제 날짜로 조회
    if TEST_DATE:
        target_dt = datetime.datetime.strptime(TEST_DATE, "%Y-%m-%d")
    else:
        target_dt = now - datetime.timedelta(days=1)

    yesterday_str = target_dt.strftime("%Y-%m-%d")
    yesterday_display = target_dt.strftime("%m월 %d일")

    # 1. 경기 결과 및 최신 뉴스 수집
    game_results = get_yesterday_kbo_results(yesterday_str)
    news_items = get_baseball_news(5)

    # 2. 친근한 인사말 및 경기 결과 문구 작성
    message_lines = [
        "안녕하세요 KBO 팬 여러분들! ⚾",
        f"어제({yesterday_display})의 경기 결과 알려드릴게요!\n",
    ]

    if game_results:
        for res in game_results:
            message_lines.append(res)
    else:
        message_lines.append(
            "- 어제는 진행된 KBO 공식 경기가 없었어요. (휴식일 또는 비시즌)"
        )

    message_lines.append("\n---\n")

    # 3. 최신 뉴스 섹션 작성
    message_lines.append("📰 **아래는 최신 뉴스에 대한 정보들이에요!**\n")
    if not news_items:
        message_lines.append("- 오늘 아침에는 새로 올라온 뉴스가 아직 없네요.")
    else:
        for item in news_items:
            message_lines.append(
                f"- [{item['title']}]({item['link']}) `({item['press']})`"
            )

    # 4. 마무리 인사말
    message_lines.append("\n오늘도 활기차고 좋은 하루 보내세요! 🙌")

    full_description = "\n".join(message_lines)

    payload = {
        "username": "⚾ KBO 모닝 메이트",
        "embeds": [
            {
                "title": f"☀️ {today_str} KBO 아침 소식지",
                "description": full_description,
                "color": 0x002B5B,
                "footer": {
                    "text": f"발송 시각: {now.strftime('%H:%M')} | 매일 아침 9시 여러분을 찾아갑니다"
                },
            }
        ],
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code in (200, 204):
            print(
                f"✅ [{today_str}] 디스코드 뉴스레터 발송 성공! (조회 날짜: {yesterday_str})"
            )
        else:
            print(
                f"❌ 발송 실패 (HTTP {response.status_code}): {response.text}"
            )
            sys.exit(1)
    except Exception as e:
        print(f"❌ 요청 중 에러 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    send_discord_newsletter()

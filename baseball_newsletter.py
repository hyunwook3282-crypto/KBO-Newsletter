import datetime
import os
import sys
import urllib.parse
import feedparser
import pytz
import requests

# GitHub Secrets에 등록한 환경변수 불러오기
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")


def get_baseball_news(max_items=5):
    """구글 뉴스 RSS에서 최신 KBO 및 야구 뉴스를 가져옵니다."""
    query = urllib.parse.quote("KBO OR 프로야구")
    rss_url = (
        f"https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    )

    feed = feedparser.parse(rss_url)
    news_list = []

    for entry in feed.entries[:max_items]:
        # 구글 뉴스 제목 형식("기사제목 - 언론사")에서 언론사 분리
        title_parts = entry.title.rsplit(" - ", 1)
        clean_title = title_parts[0]
        press = title_parts[1] if len(title_parts) > 1 else "뉴스"

        news_list.append(
            {"title": clean_title, "press": press, "link": entry.link}
        )
    return news_list


def send_discord_newsletter():
    """수집한 야구 뉴스를 디스코드 임베드 메시지로 전송합니다."""
    if not DISCORD_WEBHOOK_URL:
        print("❌ 오류: DISCORD_WEBHOOK_URL 환경변수가 설정되지 않았습니다.")
        print("GitHub 저장소의 Settings -> Secrets에 웹훅 URL을 등록해주세요.")
        sys.exit(1)

    kst = pytz.timezone("Asia/Seoul")
    now = datetime.datetime.now(kst)
    today_str = now.strftime("%Y년 %m월 %d일")

    news_items = get_baseball_news(5)

    # 뉴스 본문 마크다운 생성
    if not news_items:
        description = "현재 새로 업데이트된 주요 야구 뉴스가 없습니다."
    else:
        description = "오늘의 주요 야구 소식을 전해드립니다!\n\n"
        for idx, item in enumerate(news_items, 1):
            description += f"**{idx}. [{item['title']}]({item['link']})** `({item['press']})`\n\n"

    # 디스코드에 보낼 데이터(Payload) 구성
    payload = {
        "username": "⚾ KBO 모닝 브리핑",
        "embeds": [
            {
                "title": f"☀️ {today_str} 아침 야구 뉴스레터",
                "description": description,
                "color": 0x002B5B,  # 네이비 색상
                "footer": {
                    "text": f"발송 시각: {now.strftime('%H:%M:%S')} (KST) | GitHub Actions 자동 발송"
                },
            }
        ],
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code in (200, 204):
            print(f"✅ [{today_str}] 디스코드 뉴스레터 발송 성공!")
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

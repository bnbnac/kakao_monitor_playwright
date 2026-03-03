"""
카카오톡 채널 크롤러 - Playwright 버전
Ubuntu 20.04 ARM64 최적화

Playwright는 Selenium보다 가볍고 ARM64에서도 잘 작동합니다.
"""

import asyncio
from collections import deque
import re
import logging
import os
from datetime import datetime, timedelta

import httpx
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# .env 파일 로드
load_dotenv()

# 로깅 설정
logger = logging.getLogger(__name__)

MAX_SEEN_POSTS = 5


class KakaoChannelMonitor:
    def __init__(self, channel_url, webhook_url, debug=False):
        self.channel_url = channel_url
        self.webhook_url = webhook_url
        self.webhook_type = self._detect_webhook_type(webhook_url)
        self.debug = debug
        self.seen_posts = deque(maxlen=MAX_SEEN_POSTS)
        self._first_run = True
        self._browser = None
        self._playwright = None

    @staticmethod
    def _detect_webhook_type(url):
        """Webhook URL에서 플랫폼 타입 감지"""
        if "discord.com" in url or "discordapp.com" in url:
            return "discord"
        if "hooks.slack.com" in url:
            return "slack"
        return "slack"  # 기본값

    async def _ensure_browser(self):
        """브라우저 인스턴스가 없으면 생성, 있으면 재사용"""
        if self._browser is None or not self._browser.is_connected():
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            logger.info("브라우저 시작 중...")
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )
        return self._browser

    async def close(self):
        """브라우저 및 Playwright 리소스 정리"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def fetch_posts(self):
        """카카오톡 채널에서 최신 n월m 게시물 1개를 찾아 반환"""
        posts = []
        page = None
        meal_pattern = re.compile(r'\d{1,2}월\s?\d{1,2}')

        try:
            browser = await self._ensure_browser()
            page = await browser.new_page()

            logger.info("페이지 로딩 중: %s", self.channel_url)
            await page.goto(self.channel_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            if self.debug:
                content = await page.content()
                with open('page_debug.html', 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.debug("메인 페이지 소스를 page_debug.html에 저장했습니다.")

            # 첫 번째 n월m일 링크만 찾기
            links = await page.query_selector_all('a')
            found = None

            for link in links:
                try:
                    text = (await link.inner_text()).strip()
                    if meal_pattern.search(text):
                        href = await link.get_attribute('href')
                        if href:
                            if not href.startswith('http'):
                                href = f"https://pf.kakao.com{href}"
                            found = {'text': text, 'href': href}
                            break
                except Exception:
                    continue

            if not found:
                logger.warning("n월m일 링크를 찾지 못했습니다.")
                if self.debug:
                    content = await page.content()
                    with open('page_debug.html', 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.warning("page_debug.html을 확인하여 HTML 구조를 파악하세요.")
            else:
                logger.info("링크 발견: %s -> %s", found['text'], found['href'])
                posts.append({
                    'id': found['href'],
                    'title': found['text'],
                    'url': found['href'],
                })

        except Exception as e:
            logger.error("게시물 가져오기 오류: %s", e)
        finally:
            if page:
                await page.close()

        return posts

    def _build_slack_message(self, post):
        """Slack 메시지 생성 (제목 + 링크)"""
        return {
            "text": f"{post['title']}\n{post['url']}"
        }

    def _build_discord_message(self, post):
        """Discord 메시지 생성 (제목 + 링크)"""
        return {
            "content": f"{post['title']}\n{post['url']}"
        }

    async def _send_notification(self, post):
        """Webhook으로 새 게시물 알림 전송 (Slack/Discord 자동 감지)"""
        if self.webhook_type == "discord":
            message = self._build_discord_message(post)
        else:
            message = self._build_slack_message(post)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=message,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                response.raise_for_status()
            logger.info("[%s] 알림 전송 완료: %s", self.webhook_type, post['title'][:50])
            return True
        except Exception as e:
            logger.error("[%s] 알림 전송 오류: %s", self.webhook_type, e)
            return False

    async def check_new_posts(self):
        """새 게시물 확인 및 알림"""
        posts = await self.fetch_posts()
        new_posts = []

        for post in posts:
            if post['id'] not in self.seen_posts:
                new_posts.append(post)
                self.seen_posts.append(post['id'])

                if not self._first_run and self.webhook_url != "test_mode":
                    success = await self._send_notification(post)
                    if success:
                        await asyncio.sleep(1)

        if self._first_run:
            logger.info("초기 실행: 기존 게시물 %d개 등록 (알림 생략)", len(new_posts))
            self._first_run = False
        elif new_posts:
            logger.info("%d개의 새 게시물을 발견했습니다!", len(new_posts))
        else:
            logger.info("새 게시물이 없습니다.")

        return new_posts

    async def test_connection(self):
        """연결 테스트"""
        logger.info("=" * 60)
        logger.info("연결 테스트 시작")
        logger.info("=" * 60)

        logger.info("1. 카카오톡 채널 접속 및 파싱 테스트...")
        posts = await self.fetch_posts()

        if posts:
            logger.info("게시물 발견: %s -> %s", posts[0]['title'], posts[0]['url'])
        else:
            logger.warning("게시물을 찾지 못했습니다.")
            return False

        if self.webhook_url != "test_mode":
            logger.info("2. Webhook 연결 테스트 (%s)...", self.webhook_type)

            if self.webhook_type == "discord":
                test_message = {"content": "카카오톡 채널 모니터링 테스트 메시지입니다!"}
            else:
                test_message = {"text": "카카오톡 채널 모니터링 테스트 메시지입니다!"}

            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.webhook_url,
                        json=test_message,
                        timeout=10
                    )
                if response.status_code in (200, 204):
                    logger.info("Webhook 연결 성공!")
                else:
                    logger.warning("Webhook 응답 코드: %d", response.status_code)
                    return False
            except Exception as e:
                logger.error("Webhook 연결 실패: %s", e)
                return False

        logger.info("=" * 60)
        logger.info("모든 테스트 완료!")
        logger.info("=" * 60)
        return True

    async def run(self, interval=300):
        """주기적으로 새 게시물 확인"""
        logger.info("=" * 60)
        logger.info("카카오톡 채널 -> Slack 모니터링 시작")
        logger.info("=" * 60)
        logger.info("채널 URL: %s", self.channel_url)
        logger.info("확인 주기: %d초 (%d분)", interval, interval // 60)
        logger.info("저장된 게시물: %d개", len(self.seen_posts))
        logger.info("종료하려면 Ctrl+C를 누르세요.")
        logger.info("=" * 60)

        try:
            while True:
                try:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    logger.info("[%s] 새 게시물 확인 중...", timestamp)

                    await self.check_new_posts()

                    next_check = datetime.now() + timedelta(seconds=interval)
                    logger.info("다음 확인: %s", next_check.strftime('%H:%M:%S'))

                    await asyncio.sleep(interval)

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error("오류 발생: %s", e)
                    logger.info("%d초 후 재시도...", interval)
                    await asyncio.sleep(interval)

        except KeyboardInterrupt:
            logger.info("=" * 60)
            logger.info("모니터링을 종료합니다.")
            logger.info("총 확인한 게시물: %d개", len(self.seen_posts))
            logger.info("=" * 60)
        finally:
            await self.close()


def _setup_logging(debug=False):
    """로깅 설정"""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def main():
    # 설정 (.env 또는 환경변수에서 읽기)
    channel_url = os.getenv("KAKAO_CHANNEL_URL", "https://pf.kakao.com/_aZJxon/posts")
    webhook_url = os.getenv("WEBHOOK_URL", "")
    check_interval = int(os.getenv("CHECK_INTERVAL", "300"))
    debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")

    _setup_logging(debug)

    if not webhook_url:
        logger.warning("=" * 60)
        logger.warning("Webhook URL이 설정되지 않았습니다!")
        logger.warning("=" * 60)
        logger.info("설정 방법:")
        logger.info("  1. .env 파일에 WEBHOOK_URL=https://... 추가")
        logger.info("  2. Discord: https://discord.com/api/webhooks/...")
        logger.info("  3. Slack: https://hooks.slack.com/services/...")
        logger.info("=" * 60)
        webhook_url = "test_mode"

    monitor = KakaoChannelMonitor(channel_url, webhook_url, debug=debug)

    try:
        await monitor.test_connection()

        if webhook_url != "test_mode":
            # 비대화형 환경에서도 동작하도록 자동 시작
            logger.info("테스트 완료. 모니터링을 시작합니다...")

        await monitor.run(interval=check_interval)
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())

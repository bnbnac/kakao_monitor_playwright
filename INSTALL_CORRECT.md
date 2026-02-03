# 카카오톡 채널 크롤러 - 올바른 설치 가이드

## ⚠️ 중요: BeautifulSoup으로는 불가능합니다!

카카오톡 채널(`pf.kakao.com`)은 **JavaScript로 렌더링되는 SPA**(Single Page Application)입니다.
따라서 일반 requests + BeautifulSoup로는 내용을 가져올 수 없습니다.

## ✅ 해결책: Playwright 사용

Playwright는:
- Selenium보다 가볍고 빠름
- ARM64 공식 지원
- 헤드리스 모드 안정적
- 비동기 처리 지원

## 🚀 설치 방법

### 1. 시스템 준비

```bash
# 시스템 업데이트
sudo apt update
sudo apt upgrade -y

# 필수 의존성 설치
sudo apt install -y python3-pip python3-dev
```

### 2. Python 패키지 설치

```bash
# Playwright 및 의존성 설치
pip3 install --user playwright requests

# Playwright 브라우저 설치 (Chromium)
python3 -m playwright install chromium

# 브라우저 의존성 설치
python3 -m playwright install-deps chromium
```

**ARM64에서 문제가 있다면:**
```bash
# 시스템 레벨 설치
sudo pip3 install playwright
sudo python3 -m playwright install --with-deps chromium
```

### 3. 스크립트 설정

```bash
# 작업 디렉토리 생성
mkdir -p ~/kakao-monitor
cd ~/kakao-monitor

# 스크립트 복사 (다운로드한 파일)
cp /path/to/kakao_monitor_playwright.py ~/kakao-monitor/

# 설정 수정
nano kakao_monitor_playwright.py
```

**수정할 부분:**
```python
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
```

### 4. 테스트 실행

```bash
cd ~/kakao-monitor
python3 kakao_monitor_playwright.py
```

## 🔧 문제 해결

### Playwright 설치 오류

**오류: `playwright install` 실패**

```bash
# 방법 1: 수동 설치
wget https://playwright.azureedge.net/builds/chromium/1000/chromium-linux-arm64.zip
unzip chromium-linux-arm64.zip -d ~/.cache/ms-playwright/

# 방법 2: Docker 사용 (권장)
# 아래 Docker 섹션 참조
```

### ARM64 브라우저 지원 이슈

ARM64에서 Chromium 설치가 안 될 경우:

```bash
# Firefox 사용 (대안)
python3 -m playwright install firefox
python3 -m playwright install-deps firefox
```

스크립트에서 수정:
```python
# browser = await p.chromium.launch(...)
browser = await p.firefox.launch(...)  # Firefox로 변경
```

## 🐳 Docker 사용 (가장 안정적)

ARM64에서 가장 확실한 방법은 Docker 사용:

### Dockerfile 생성

```dockerfile
FROM python:3.9-slim

# 작업 디렉토리
WORKDIR /app

# 의존성 설치
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
RUN pip install playwright requests

# Playwright 브라우저 설치
RUN playwright install chromium
RUN playwright install-deps chromium

# 스크립트 복사
COPY kakao_monitor_playwright.py /app/

# 볼륨 (데이터 저장용)
VOLUME /app/data

# 실행
CMD ["python", "kakao_monitor_playwright.py"]
```

### Docker로 실행

```bash
# 이미지 빌드
docker build -t kakao-monitor .

# 컨테이너 실행
docker run -d \
  --name kakao-monitor \
  --restart unless-stopped \
  -v $(pwd)/data:/app/data \
  kakao-monitor

# 로그 확인
docker logs -f kakao-monitor

# 중지
docker stop kakao-monitor

# 재시작
docker start kakao-monitor
```

## 📋 대안: Puppeteer (Node.js)

Python이 복잡하다면 Node.js + Puppeteer 사용:

```javascript
// kakao-monitor.js
const puppeteer = require('puppeteer');
const axios = require('axios');

const CHANNEL_URL = 'https://pf.kakao.com/_aZJxon/posts';
const SLACK_WEBHOOK = 'YOUR_WEBHOOK_URL';

async function checkPosts() {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  
  await page.goto(CHANNEL_URL, { waitUntil: 'networkidle2' });
  await page.waitForTimeout(3000);
  
  const posts = await page.evaluate(() => {
    // 게시물 추출 로직
    return Array.from(document.querySelectorAll('article')).map(el => ({
      title: el.innerText.split('\n')[0],
      content: el.innerText
    }));
  });
  
  await browser.close();
  
  // Slack 전송 로직...
  for (const post of posts) {
    await axios.post(SLACK_WEBHOOK, { text: post.title });
  }
}

setInterval(checkPosts, 5 * 60 * 1000); // 5분마다
```

설치:
```bash
npm install puppeteer axios
node kakao-monitor.js
```

## 🎯 권장 방법 요약

| 환경 | 권장 방법 | 난이도 |
|------|----------|--------|
| **일반 서버** | Playwright | ⭐⭐ |
| **ARM64 (문제 있음)** | Docker | ⭐⭐⭐ |
| **Node.js 선호** | Puppeteer | ⭐⭐ |
| **간단한 구성** | 크롤링 서비스 (외부) | ⭐ |

## 🔍 실제 작동 확인

설치 후 반드시 테스트:

```bash
python3 kakao_monitor_playwright.py
```

다음이 나타나야 정상:
```
✓ 선택자 'article'로 X개 요소 발견
✓ X개의 게시물을 파싱했습니다.
```

만약 `⚠️ 게시물 요소를 찾지 못했습니다.` 나오면:
1. `page_debug.html` 파일 열기
2. HTML 구조 확인
3. 선택자 수정 필요

## 💡 최종 팁

1. **처음 실행 시** `page_debug.html`이 생성됩니다 → 페이지 구조 확인용
2. **seen_posts.json** 파일로 중복 방지
3. **5분 주기 권장** (너무 자주 확인하면 차단 위험)
4. **로그 모니터링** 필수

## 📞 여전히 안 된다면?

1. `page_debug.html` 파일 내용 확인
2. 브라우저 버전 확인: `python3 -m playwright --version`
3. 수동으로 URL 접속하여 로그인/차단 여부 확인
4. VPN/프록시 사용 고려

---

**결론: BeautifulSoup만으로는 불가능하며, Playwright나 Selenium 같은 브라우저 자동화 도구가 반드시 필요합니다.**

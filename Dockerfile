FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

COPY kakao_monitor_playwright.py .

CMD ["python", "kakao_monitor_playwright.py"]

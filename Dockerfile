FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium + all its system dependencies
RUN playwright install --with-deps chromium

COPY . .

# Non-root user for security
RUN useradd -m scraper && \
    mkdir -p /home/scraper/.cache && \
    cp -r /root/.cache/ms-playwright /home/scraper/.cache/ms-playwright && \
    chown -R scraper:scraper /app /home/scraper/.cache

USER scraper
ENV PLAYWRIGHT_BROWSERS_PATH=/home/scraper/.cache/ms-playwright

CMD ["python", "-m", "src.main"]

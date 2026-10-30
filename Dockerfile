# Selenium automation with Google Chrome and ChromeDriver.
# The container searches Al Jazeera, summarizes the first article,
# and starts the REST API on port 7000.
FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    CHROME_VERSION=156.0.8078.80

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl unzip \
        fonts-liberation \
        libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
        libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
        libnspr4 libnss3 libpango-1.0-0 libcairo2 \
        libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
        libxrandr2 libxshmfence1 libxss1 \
        && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/chrome.zip \
        "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && unzip -q /tmp/chrome.zip -d /opt \
    && ln -sf /opt/chrome-linux64/chrome /usr/bin/google-chrome \
    && curl -fsSL -o /tmp/chromedriver.zip \
        "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip -q /tmp/chromedriver.zip -d /opt \
    && ln -sf /opt/chromedriver-linux64/chromedriver /usr/bin/chromedriver \
    && chmod +x /opt/chrome-linux64/chrome /opt/chromedriver-linux64/chromedriver \
    && rm -f /tmp/chrome.zip /tmp/chromedriver.zip

WORKDIR /app
COPY requirements.txt wheels/selenium-4.52.0-py3-none-any.whl ./
RUN pip install --no-cache-dir ./selenium-4.52.0-py3-none-any.whl \
    && pip install --no-cache-dir flask==3.1.2
COPY app.py summarizer.py ./

EXPOSE 7000
ENTRYPOINT ["python", "app.py"]

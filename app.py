import re
import shutil
import threading
import time
import urllib.parse

from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from summarizer import summarize

# Last three digits of SP22-BCS-108 are 108.
# 108 % 20 + 1 = 9 -> Al Jazeera Media Network
REGISTRATION = "SP22-BCS-108"
NEWS_SOURCE = "Al Jazeera Media Network"
SITE = "https://www.aljazeera.com"
SECTIONS = ("/news/", "/features/", "/opinions/", "/opinion/", "/economy/", "/sports/", "/gallery/")
SKIP_PARTS = ("/video/live", "/account", "/search", "/tag/", "/author/", "/about")

app = Flask(__name__)
_driver = None
_lock = threading.Lock()


def reset_driver():
    global _driver
    if _driver is not None:
        try:
            _driver.quit()
        except Exception:
            pass
        _driver = None
    shutil.rmtree("/tmp/chrome-profile", ignore_errors=True)


def chrome_driver():
    global _driver
    if _driver is not None:
        try:
            _driver.current_url
            return _driver
        except Exception:
            reset_driver()

    options = Options()
    options.binary_location = "/opt/chrome-linux64/chrome"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-http2")
    options.add_argument("--disable-quic")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--lang=en-US")
    options.add_argument("--user-data-dir=/tmp/chrome-profile")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )
    service = Service("/usr/bin/chromedriver")
    _driver = webdriver.Chrome(service=service, options=options)
    _driver.set_page_load_timeout(35)
    _driver.set_script_timeout(35)
    _driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return _driver


def dismiss_banners(driver):
    for selector in ("#onetrust-accept-btn-handler", "button[aria-label*='Accept']"):
        try:
            button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            button.click()
            return
        except Exception:
            continue


def open_page(driver, url):
    try:
        driver.get(url)
    except Exception:
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass


def article_url(href):
    if not href:
        return ""
    parsed = urllib.parse.urlparse(href)
    if "duckduckgo.com" in parsed.netloc and "uddg=" in (parsed.query or ""):
        href = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        parsed = urllib.parse.urlparse(href)
    if "aljazeera.com" not in parsed.netloc:
        return ""
    path = parsed.path or ""
    if any(part in path for part in SKIP_PARTS):
        return ""
    if not any(path.startswith(section) for section in SECTIONS):
        return ""
    if path.rstrip("/").count("/") < 3:
        return ""
    return urllib.parse.urlunparse(parsed._replace(query="", fragment=""))


def site_search(driver, keyword):
    encoded = urllib.parse.quote(keyword)
    open_page(driver, f"{SITE}/search/{encoded}")
    dismiss_banners(driver)
    WebDriverWait(driver, 18).until(
        lambda current: any(
            article_url(anchor.get_attribute("href"))
            for anchor in current.find_elements(By.CSS_SELECTOR, "a[href]")
        )
    )
    words = [word for word in re.split(r"\W+", keyword.lower()) if len(word) > 2]
    found = []
    for anchor in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        url = article_url(anchor.get_attribute("href"))
        if url and url not in found:
            found.append(url)
    found.sort(key=lambda url: (0 if any(word in url.lower() for word in words) else 1, found.index(url) if url in found else 0))
    # Stable preference: keyword matches first, original order otherwise.
    preferred = [url for url in found if any(word in url.lower() for word in words)]
    return (preferred or found)[0]


def web_search(driver, keyword):
    query = urllib.parse.quote(f"site:aljazeera.com {keyword}")
    open_page(driver, f"https://html.duckduckgo.com/html/?q={query}")
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a.result__a, a[href]"))
    )
    for anchor in driver.find_elements(By.CSS_SELECTOR, "a.result__a, a[href]"):
        url = article_url(anchor.get_attribute("href"))
        if url:
            return url
    raise RuntimeError(f"No Al Jazeera article found for {keyword!r}")


def first_result_url(driver, keyword):
    try:
        return site_search(driver, keyword)
    except Exception:
        return web_search(driver, keyword)


def read_article(driver, url):
    open_page(driver, url)
    dismiss_banners(driver)
    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "h1"))
    )
    title = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
    paragraphs = []
    for paragraph in driver.find_elements(By.CSS_SELECTOR, "div.wysiwyg p, article p, main p"):
        text = " ".join(paragraph.text.split())
        if len(text) > 60:
            paragraphs.append(text)
        if len(paragraphs) >= 4:
            break
    body = " ".join(paragraphs)
    if title and title not in body:
        body = f"{title}. {body}".strip()
    return body


def lookup(keyword):
    last_error = None
    for _attempt in range(2):
        try:
            driver = chrome_driver()
            url = first_result_url(driver, keyword)
            summary = summarize(read_article(driver, url))
            if not summary:
                raise RuntimeError("Article had no text to summarize")
            return url, summary
        except Exception as exc:
            last_error = exc
            reset_driver()
            time.sleep(1)
    raise RuntimeError(f"Could not summarize an Al Jazeera article for {keyword!r}") from last_error


@app.get("/")
def home():
    return (
        "<!doctype html><html><head><title>SP22-BCS-108</title></head>"
        "<body><h1>SP22-BCS-108</h1>"
        "<p>Registration Number: SP22-BCS-108</p>"
        "<p>News source: Al Jazeera Media Network</p>"
        "<p>API: /get?keyword=climate</p></body></html>"
    )


@app.get("/get")
def get_news():
    keyword = (request.args.get("keyword") or "").strip()
    if not keyword:
        return jsonify({"error": "keyword is required"}), 400
    with _lock:
        url, summary = lookup(keyword)
    return jsonify(
        {
            "registration": REGISTRATION,
            "newssource": NEWS_SOURCE,
            "keyword": keyword,
            "url": url,
            "summary": summary,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000, threaded=False)

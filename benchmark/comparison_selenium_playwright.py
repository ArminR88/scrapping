import os
import time
import asyncio
import statistics
import pandas as pd
from time import perf_counter
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from playwright.async_api import async_playwright

TEST_URL = "http://quotes.toscrape.com"
NUM_RUNS = 5  # Number of times to run each test for a reliable average
WARMUP = 3     # Warm-up runs to stabilize caches/initialization

# ensure webdriver-manager uses a writable local cache (avoid writing to /app/.wdm)
os.environ.setdefault("WDM_LOCAL", "/tmp/.wdm")
wdm_local = os.environ.get("WDM_LOCAL", "/tmp/.wdm")
try:
    os.makedirs(wdm_local, exist_ok=True)
except Exception:
    pass

# try to use webdriver-manager if available (optional)
try:
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    _HAS_WDM = True
except Exception:
    Service = None
    ChromeDriverManager = None
    _HAS_WDM = False

BRAVE_PATH = os.getenv("BRAVE_EXECUTABLE")  # optional path to Brave binary

# --- 1. Selenium Test Function ---
def run_selenium():
    """
    Try Chromium-family first (Brave / system Chrome / Playwright-installed chromium),
    then fall back to Firefox. Uses webdriver-manager when available.
    """
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # detect candidate Chromium binary locations (BRAVE, Playwright, system)
    def find_playwright_chromium(playwright_path):
        # Typical chromium headless binary locations under PLAYWRIGHT_BROWSERS_PATH
        if not playwright_path:
            return None
        candidates = []
        for root, dirs, files in os.walk(playwright_path):
            if 'headless_shell' in files or 'chrome' in files or 'headless_shell' in root:
                # prefer an explicit headless_shell or chrome executable
                candidate = os.path.join(root, 'headless_shell') if 'headless_shell' in files else os.path.join(root, 'chrome')
                if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                    return candidate
        return None

    pw_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or os.environ.get("PLAYWRIGHT_BROWSERS_PATH".lower())
    playwright_chrome = find_playwright_chromium(pw_path)

    candidates = [
        BRAVE_PATH,
        playwright_chrome,
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chrome",
    ]
    chrome_binary = next((p for p in candidates if p and os.path.isfile(p) and os.access(p, os.X_OK)), None)
    if chrome_binary:
        options.binary_location = chrome_binary

    start_time = perf_counter()

    # helper to attempt starting a Chrome/Chromium driver
    def try_start_chrome():
        try:
            if _HAS_WDM:
                driver_path = ChromeDriverManager().install()
                driver = webdriver.Chrome(service=Service(driver_path), options=options)
            else:
                driver = webdriver.Chrome(options=options)
            return driver
        except Exception as e:
            raise e

    # helper to attempt starting a Firefox driver
    def try_start_firefox():
        try:
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            from selenium.webdriver.firefox.service import Service as FirefoxService
            try:
                # webdriver-manager Gecko support (optional)
                from webdriver_manager.firefox import GeckoDriverManager
                gpath = GeckoDriverManager().install()
                fservice = FirefoxService(gpath)
                fopts = FirefoxOptions()
                fopts.add_argument("--headless")
                fopts.add_argument("--no-sandbox")
                fopts.add_argument("--disable-dev-shm-usage")
                driver = webdriver.Firefox(service=fservice, options=fopts)
            except Exception:
                # fallback to system geckodriver / firefox if present
                fopts = FirefoxOptions()
                fopts.add_argument("--headless")
                driver = webdriver.Firefox(options=fopts)
            return driver
        except Exception as e:
            raise e

    # attempt Chrome first, then Firefox
    driver = None
    try:
        try:
            driver = try_start_chrome()
        except Exception as chrome_err:
            # try firefox if chrome fails
            try:
                driver = try_start_firefox()
            except Exception as firefox_err:
                # surface both errors for debugging
                print(f"  [Selenium] Chrome start error: {chrome_err}")
                print(f"  [Selenium] Firefox start error: {firefox_err}")
                return float("inf")

    except Exception as e:
        print(f"  [Selenium] Driver start error: {e}")
        return float("inf")

    try:
        driver.get(TEST_URL)
        quotes = driver.find_elements(By.CLASS_NAME, "quote")
        elapsed = perf_counter() - start_time
        print(f"  [Selenium] Found {len(quotes)} quotes in {elapsed:.3f}s.")
    except Exception as e:
        print(f"  [Selenium] Error during navigation: {e}")
        elapsed = float("inf")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return elapsed

# --- 2. Playwright Test Function (Asynchronous) ---
async def run_playwright_async():
    """
    Measures time including browser launch and page navigation, comparable to Selenium above.
    """
    try:
        async with async_playwright() as p:
            # only set executable_path if Brave binary exists and is executable
            launch_kwargs = {"headless": True}
            brave_candidate = BRAVE_PATH if BRAVE_PATH and os.path.isfile(BRAVE_PATH) and os.access(BRAVE_PATH, os.X_OK) else None
            if brave_candidate:
                launch_kwargs["executable_path"] = brave_candidate
            start_time = perf_counter()
            browser = await p.chromium.launch(**launch_kwargs)
            page = await browser.new_page()
            await page.goto(TEST_URL)
            quotes = await page.locator(".quote").all()
            elapsed = perf_counter() - start_time
            print(f"  [Playwright] Found {len(quotes)} quotes in {elapsed:.3f}s.")
            await browser.close()
            return elapsed
    except Exception as e:
        print(f"  [Playwright] Error: {e}")
        return float("inf")

def run_playwright_sync():
    return asyncio.run(run_playwright_async())

# --- 3. Benchmark harness ---
def benchmark(func, runs=NUM_RUNS, warmup=WARMUP):
    # warmup
    for i in range(warmup):
        _ = func()
    times = []
    for i in range(runs):
        t = func()
        times.append(t)
    # filter out failed runs (inf)
    successful = [t for t in times if t != float("inf")]
    stats = {
        "runs": runs,
        "successful": len(successful),
        "mean": statistics.mean(successful) if successful else float("inf"),
        "median": statistics.median(successful) if successful else float("inf"),
        "stdev": statistics.stdev(successful) if len(successful) > 1 else 0.0,
        "min": min(successful) if successful else float("inf"),
        "max": max(successful) if successful else float("inf"),
    }
    return stats, times

def main(runs=NUM_RUNS, warmup=WARMUP):
    print(f"Benchmarking each tool with {runs} runs (+{warmup} warmup)...\n")

    print("Running Selenium tests...")
    s_stats, s_times = benchmark(run_selenium, runs=runs, warmup=warmup)

    print("\nRunning Playwright tests...")
    p_stats, p_times = benchmark(run_playwright_sync, runs=runs, warmup=warmup)

    # Summarize with pandas for easy inspection
    df = pd.DataFrame([
        {
            "tool": "selenium",
            "runs": s_stats["runs"],
            "successful": s_stats["successful"],
            "mean_s": s_stats["mean"],
            "median_s": s_stats["median"],
            "stdev_s": s_stats["stdev"],
            "min_s": s_stats["min"],
            "max_s": s_stats["max"],
        },
        {
            "tool": "playwright",
            "runs": p_stats["runs"],
            "successful": p_stats["successful"],
            "mean_s": p_stats["mean"],
            "median_s": p_stats["median"],
            "stdev_s": p_stats["stdev"],
            "min_s": p_stats["min"],
            "max_s": p_stats["max"],
        },
    ])
    print("\nSummary:")
    print(df.to_string(index=False))


if __name__ == "__main__":    main()
# Python Scraping Project

This project contains tools and scripts for web scraping, with a focus on comparing different libraries to select the best tool for the job.

## Performance Benchmark: Playwright vs. Selenium

The script `comparison_selenium_playwright.py` provides a direct performance comparison between Playwright and Selenium. It runs a series of automated scraping tasks with both libraries and measures the time taken, including browser startup and element location.

### Conclusion

Based on the benchmark results, **Playwright** was selected as the primary tool for the main crawling implementation in this project. It consistently demonstrated faster execution times and a more stable, modern API.

### How to Run the Benchmark

The comparison can be run inside the containerized environment to ensure consistent results.

1.  **Build the container image:**
    ```bash
    podman build -t scrapping .
    ```

2.  **Run the benchmark script:**
    ```bash
    podman run --rm -it --shm-size=1g scrapping
    ```
    This command executes `comparison_selenium_playwright.py` and will output a summary table comparing the performance metrics (mean, median, stdev) for both tools.

## Main Crawler

The main scraping logic will be built using Playwright.

*(Placeholder: Instructions for running the main crawler will be added here once it is developed.)*

# Asynchronous Web Crawler (Playwright + httpx)

A robust, three-stage async crawler with discovery, HTML extraction, and dual-mode downloads. Built on Playwright for rendering and httpx for efficient file transfers, with strict timeouts and audit logging.

## Quick Start

- Python 3.10+ recommended
- Install dependencies:
  - `pip install -r requirements.txt`
  - `python -m playwright install` (required one-time)
- Configure:
  - Edit `crawler_config.json` (see “Configuration”)
- Run:
  - `python exceution.py`

## Configuration

File: `crawler_config.json`
- `crawl_settings.start_urls`: list of entry URLs (same-origin crawl enforced)
- `crawl_settings.max_depth`: link traversal depth (default 15)
- `crawl_settings.network_timeout_seconds`: per-request timeout in seconds (default 30.0)
- `debugging.headless_mode`: currently not wired into code; browser runs headless=True by default

Example:
```
{
  "crawl_settings": {
    "start_urls": ["https://file-examples.com/index.php/sample-documents-download/"],
    "max_depth": 2,
    "network_timeout_seconds": 30.0
  },
  "debugging": {
    "headless_mode": true
  }
}
```

## What It Does

- Stage 1: Discovery
  - Crawls same-domain links, extracts href/data-url/data-href and onclick targets
  - Persists:
    - `discovery/urls_to_scrape.txt` (HTML pages)
    - `discovery/files_to_download.txt` (assets including PDFs, docs)
- Stage 2: Extraction (HTML)
  - Uses Playwright with `domcontentloaded` and a short 200ms wait
  - Saves HTML to `content/`
  - Audits failures in `rejections/scrape_failures.txt`
- Stage 3: Download (Dual-mode)
  - Attempt 1 (httpx): HEAD check for Content-Type/Length, size guard (50MB), then streamed GET
  - Attempt 2 (Playwright): robust fallback for JS/redirect-driven downloads
  - Saves files to `files/`
  - Audits rejections/failures in `rejections/download_rejections.txt` and `rejections/download_failures.txt`

## Output Layout

Under `scraped_data_YYYY_MM_DD/`:
- `discovery/urls_to_scrape.txt`
- `discovery/files_to_download.txt`
- `content/*.html`
- `files/*`
- `rejections/download_rejections.txt`
- `rejections/download_failures.txt`
- `rejections/scrape_failures.txt`

## Concurrency, Politeness, and Timeouts

In `web_crawler.py` (WebCrawler.__init__):
- Semaphores:
  - Discovery: 10
  - Scraping: 5
  - Downloading: 5
- Rate limit:
  - `rate_limit_delay = 0.2` seconds per-domain
- Safety timeout:
  - `task_timeout = max(5.0, network_timeout + 5.0)`
- Max file size:
  - `max_file_size_bytes = 50 * 1024 * 1024` (50MB)

All long-running operations (Playwright page.goto/expect_download and httpx HEAD/stream) are wrapped with `asyncio.wait_for(...)` using `task_timeout` to prevent hangs.

## Orchestration

File: `exceution.py`
- Loads config, runs Stage 1 (discovery), then Stage 2 and Stage 3 using persisted lists
- Uses `asyncio.gather(..., return_exceptions=True)` to prevent a single task crash
- Ensures Playwright contexts/browsers are closed after each stage

## Tuning

- Increase/decrease `max_depth` for traversal scope
- Adjust `network_timeout_seconds` for slower sites
- Tighten/relax `task_timeout` by changing the formula
- Change semaphore sizes for more/less concurrency
- Modify `rate_limit_delay` if servers respond slowly to bursts
- Adjust `max_file_size_bytes` for larger files

## Troubleshooting

- Playwright not installed:
  - Run `python -m playwright install`
- Freezes or timeouts:
  - Reduce `max_depth`, increase `network_timeout_seconds`, or adjust `task_timeout`
- Headless/visible browser:
  - Code currently hardcodes `headless=True`; see “Missing/Optional”
- Too many failures:
  - Check `rejections/*.txt` for reasons; verify domain policy (same-origin only)
- Large files aborted:
  - Increase `max_file_size_bytes` or confirm server provides correct Content-Length

## Missing/Optional Improvements

- Headless mode in config:
  - `debugging.headless_mode` exists but is not wired into code; integrate to toggle visibility
- robots.txt compliance:
  - Currently not enforced; add parsing to respect disallow rules
- Resume capabilities:
  - Discovery results persist; add incremental resume logic for Stage 2/3 retries
- Per-domain depth/rules:
  - Useful for multi-domain crawls with differing policies

## Requirements

See `requirements.txt`. After installing Playwright, run `python -m playwright install`.

## License

Add your preferred license file if needed.
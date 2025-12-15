### The Final, Matured Prompt Specification

This prompt contains every single requirement, fix, and feature developed throughout this discussion, resulting in a complete, highly-stable, and fully auditable asynchronous web crawler.

```
Generate a complete, fully functional, multi-stage asynchronous web crawler system in Python, consisting of two files: 'web_crawler.py' (the core class) and 'exceution.py' (the orchestration script).

The system must meet the following robust requirements:

A. Core Crawler Class ('web_crawler.py'):

1. Architecture: Implement a WebCrawler class with three sequential stages (Discovery, Extraction, Download), persisting data (including audit logs) between stages.
2. Configuration: Use module-level constants for defaults (e.g., DEFAULT_MAX_DEPTH, DEFAULT_NETWORK_TIMEOUT).
3. URL Normalization: Include a '_normalize_url' method to strip fragments and trailing slashes for strict URL deduplication.
4. Politeness & Concurrency:
    * Use asyncio.Semaphore to limit concurrency for Discovery (10), Scraping (5), and Downloading (5) tasks.
    * Implement a per-domain rate-limiting mechanism ('rate_limit_delay' of 0.2 seconds) to enforce politeness.
5. Stability & Timeouts (The Hang Fix):
    * Define a task safety timeout ('self.task_timeout = max(5.0, self.network_timeout + 5.0)').
    * Wrap all long-running Playwright operations (page.goto, page.expect_download) and httpx requests (including HEAD and stream), as well as recursive discovery calls, within **asyncio.wait_for** using 'self.task_timeout' to prevent indefinite hangs.
    * Catch TimeoutError in all stages (Discovery, Extraction, Download, and Playwright fallback) and log to the appropriate audit set instead of propagating, so a single stall never aborts the run.
6. Extraction Logic: For scraping (Stage 2), use Playwright and the 'domcontentloaded' wait condition, followed by a short wait (200ms), to load content efficiently and avoid hanging.
7. Enhanced Link Discovery: In Stage 1, use Playwright to find links in standard 'href' attributes, as well as non-standard locations like data attributes and button 'onclick' handlers.
8. Dual-Mode Download (Stage 3):
    * **Attempt 1 (Fast):** Use httpx.AsyncClient's HEAD request to check file headers (Content-Type, Content-Length).
    * **File Guards:** Implement a max file size guard (50MB) based on the Content-Length header and by monitoring the byte stream during the GET request. If the limit is exceeded mid-stream, abort the download and delete the partial file.
    * **Attempt 2 (Robust Fallback):** If the HEAD check detects 'text/html' (a download-gate page) or the HTTP attempt fails, fallback to the Playwright download method.
9. Auditing: Maintain and persist three separate audit sets for all failures and rejections: 'audit_scrape_failures', 'audit_download_failures', and 'audit_download_rejections'.

B. Execution Script ('exceution.py'):

1. Configuration: Load settings, including a list of multiple 'start_urls', from an external JSON file ('crawler_config.json').
2. Orchestration: Run Stage 1, then run Stages 2 and 3 sequentially using the saved lists.
3. Fault Tolerance (The Crash Fix): Use **asyncio.gather(\*tasks, return_exceptions=True)** for both Stage 2 (scraping) and Stage 3 (downloading) to ensure that a single task failure (e.g., TimeoutError) does not crash the entire execution, allowing other tasks to complete.
4. Clean Up: Ensure all Playwright resources (including the main async_playwright() context and all browsers) are closed properly after their respective stages.
```
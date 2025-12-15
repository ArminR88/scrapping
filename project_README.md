ROBUST ASYNCHRONOUS WEB CRAWLER SYSTEM
=======================================

This project implements a highly resilient, three-stage asynchronous web crawler using Python's asyncio, Playwright, and httpx. It is designed to be highly resistant to pipeline hangs (freezing) and crashes, providing comprehensive auditing for all network operations and failures.

The system is split into two files:
1. web_crawler.py: The core WebCrawler class containing all the crawling logic, concurrency controls, and persistence methods.
2. execution.py: The orchestration script that loads configuration, runs the three stages sequentially, and ensures fault-tolerant execution.

KEY FEATURES AND ARCHITECTURAL IMPROVEMENTS
---------------------------------------------

1. Layered Timeouts (Anti-Freeze): Every critical operation (page navigation, stream downloads, recursive calls) is wrapped with asyncio.wait_for to guarantee a hard stop, preventing indefinite hangs and pipeline freezing.

2. Fault Tolerance (Anti-Crash): Stages 2 and 3 use asyncio.gather(..., return_exceptions=True) to ensure that if one task fails (e.g., a timeout or HTTP 503 error), the entire pipeline does not crash, and other tasks continue processing.

3. Dual-Mode File Download:
   - Attempt 1 (Fast): Uses httpx to efficiently download files, checking the Content-Type.
   - Attempt 2 (Robust Fallback): Automatically switches to a slower, JavaScript-enabled Playwright download if the URL redirects to an HTML download-gate page or the HTTP request fails.

4. Politeness and Concurrency: Implements per-domain rate-limiting (0.2s delay) and uses asyncio.Semaphore to manage concurrency limits across discovery (10), scraping (5), and downloading (5) tasks.

5. Comprehensive Auditing: Stores separate, detailed logs for: scrape_failures, download_failures, and download_rejections.

6. File Size Guard: Enforces a 50MB maximum file size limit, monitoring both headers and the live stream to prevent excessive downloads and ensures partial files are cleaned up.


SETUP
-----

1. Prerequisites: Python 3.8+ is required.

2. Installation:
   Install the required Python packages and the Playwright browser drivers:

   pip install playwright httpx
   playwright install

3. Project Structure:
   Ensure you have the following file structure:

   .
   |-- web_crawler.py        # Core crawler logic
   |-- execution.py          # Script to run the crawler
   `-- crawler_config.json   # Configuration file


CONFIGURATION (crawler_config.json)
-----------------------------------

Example file content:

{
    "crawl_settings": {
        "start_urls": [
            "https://www.scrapethissite.com/",
            "https://another-domain.com/start-page"
        ],
        "max_depth": 3,
        "network_timeout_seconds": 30.0
    }
}

* start_urls: A list of entry URLs for the crawler.
* max_depth: The maximum recursive depth for discovery (Stage 1).
* network_timeout_seconds: Base timeout for network operations.


EXECUTION
---------

Run the orchestration script from your terminal:

python execution.py

OUTPUT STRUCTURE
----------------

All results, logs, and audit files are saved in a timestamped root directory, e.g., scraped_data_YYYY_MM_DD.

scraped_data_YYYY_MM_DD/
|-- discovery/             # Stage 1 successful outputs
|   |-- urls_to_scrape.txt
|   `-- files_to_download.txt
|-- content/               # Stage 2 scraped HTML content
|   `-- ...
|-- files/                 # Stage 3 downloaded high-value documents (PDF, DOCX, etc.)
|   `-- ...
`-- rejections/            # Audit logs for all errors and skips
    |-- scrape_failures.txt
    |-- download_failures.txt
    `-- download_rejections.txt
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
import httpx

# Import constants and the main class from the core module
from web_crawler import WebCrawler, DEFAULT_MAX_DEPTH, DEFAULT_NETWORK_TIMEOUT, DEFAULT_START_URL

# Define the location of the configuration file
CONFIG_FILE_PATH = Path("crawler_config.json")

def load_config(file_path: Path) -> dict:
    """
    Loads configuration settings from a JSON file.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found at: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

async def run_stage_2_and_3(crawler: WebCrawler):
    """
    Executes Stages 2 and 3 using the combined, deduplicated lists saved during discovery.
    This function initializes Playwright and httpx for concurrency in both stages.
    """
    p = await async_playwright().start()
    browser_stage_2 = None
    browser_stage_3 = None
    
    # --------------------------------------------------
    # --- STAGE 2: EXTRACTION (Scraping Content) ---
    # --------------------------------------------------
    
    print("\n\n############################################################")
    print("### STAGE 2: EXTRACTION (Scraping Content - Combined List) ###")
    print("############################################################")
    
    urls_to_process = crawler._load_urls_from_disk("urls_to_scrape.txt")
    if not urls_to_process:
        print("No URLs found to scrape. Skipping Stage 2.")
    else:
        print(f"Total unique URLs to scrape: {len(urls_to_process)}")
        browser_stage_2 = await p.chromium.launch(headless=True)
        try:
            # Create concurrent scraping tasks
            scrape_tasks = [
                asyncio.create_task(crawler._stage_2_scrape_single(browser_stage_2, url))
                for url in urls_to_process
            ]
            await asyncio.gather(*scrape_tasks)
        finally:
            if browser_stage_2:
                await browser_stage_2.close()
            print("STAGE 2 COMPLETE. Browser resources released.")
    
    # ------------------------------------------------------
    # --- STAGE 3: DOWNLOAD (High-Value Files) ---
    # ------------------------------------------------------

    print("\n\n############################################################")
    print("### STAGE 3: DOWNLOAD (High-Value Documents - Combined List) ###")
    print("############################################################")
    
    files_to_process = crawler._load_urls_from_disk("files_to_download.txt")
    
    # Apply the High-Value Document Filter (using the class attribute)
    high_value_files = [
        url for url in files_to_process 
        if url.lower().endswith(crawler.HIGH_VALUE_DATA_EXTENSIONS)
    ]
    
    if not high_value_files:
        print("No high-value document files found to download. Skipping Stage 3.")
    else:
        print(f"Processing {len(high_value_files)} unique high-value documents...")

        # Initialize Playwright browser for the fallback download method (Stage 3)
        browser_stage_3 = await p.chromium.launch(headless=True)
        
        # Use httpx.AsyncClient for concurrent and efficient downloads/checks
        async with httpx.AsyncClient(timeout=crawler.network_timeout) as client:
            download_tasks = []
            for url in high_value_files:
                download_tasks.append(
                    crawler._stage_3_download_single(client, browser_stage_3, url)
                )

            # Gather with exception tolerance
            results = await asyncio.gather(*download_tasks, return_exceptions=True)

            # Optional: log failures
            failures = sum(1 for r in results if r is False or isinstance(r, Exception))
            if failures:
                print(f"[STAGE 3] {failures} downloads failed or timed out.")
        
        print("STAGE 3 COMPLETE. File download tasks finished.")
        
    # --- CRITICAL FIX: Save Audit Logs after Stages 2 and 3 are complete ---
    crawler._save_discovery_results()
    # -----------------------------------------------------------------------

    if browser_stage_3:
        await browser_stage_3.close()
        
    await p.stop()
    print("Final Playwright context released.")
    print("-" * 60)
    print("Crawl and extraction process finished successfully.")
    print(f"Final output saved under: {crawler.output_root.resolve()}")


async def main():
    """
    Loads configuration, creates a single WebCrawler instance to run discovery (Stage 1)
    for all start URLs, and then executes Stages 2 & 3 on the combined results.
    """
    print(f"Loading configuration from {CONFIG_FILE_PATH}...")
    
    try:
        config = load_config(CONFIG_FILE_PATH)
    except FileNotFoundError as e:
        print(f"\n[FATAL ERROR] Cannot run: {e}")
        return
    except json.JSONDecodeError:
        print("[FATAL ERROR] Invalid JSON format in the configuration file.")
        return

    settings = config.get("crawl_settings", {})
    start_urls = settings.get("start_urls", [DEFAULT_START_URL])
    if isinstance(start_urls, str):
        start_urls = [start_urls]

    max_depth = settings.get("max_depth", DEFAULT_MAX_DEPTH)
    network_timeout = settings.get("network_timeout_seconds", DEFAULT_NETWORK_TIMEOUT)
    
    # --- PHASE 1: Unified Discovery for all URLs ---
    try:
        crawler_instance = WebCrawler(
            start_urls=start_urls, 
            max_depth=max_depth, 
            network_timeout=network_timeout
        )
        
        # Execute Stage 1. This internally calls _save_discovery_results (initial save).
        await crawler_instance.run_crawler()

    except ValueError as e:
        print(f"\n[FATAL ERROR] Could not initialize crawler: {e}")
        return
    except Exception as e:
        print(f"\n[FATAL ERROR] Unexpected error during discovery phase: {e}")
        return

    # --- PHASE 2: Execution of Stages 2 & 3 on Combined Lists ---
    print("\n\n############################################################")
    print("### STARTING COMBINED EXTRACTION AND DOWNLOAD PHASES (2 & 3) ###")
    print("############################################################")

    # Run the combined stages. This will now populate the audit sets AND save them.
    await run_stage_2_and_3(crawler_instance)


if __name__ == "__main__":
    
    try:
        # Initial check to ensure Playwright is installed
        asyncio.run(async_playwright().start()) 
    except Exception:
        print("\n[SETUP ERROR] Playwright is not initialized.")
        print("Please run: pip install playwright httpx && playwright install")
        exit(1)
        
    try:
        # Run the main execution loop
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Crawl stopped by user.")
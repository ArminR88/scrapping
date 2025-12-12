import asyncio
from web_crawler import WebCrawler

# --- Configuration for Testing ---
# Using a specific test site known for structure and content
TEST_URL = "https://webscraper.io/test-sites/e-commerce/static" 
TEST_MAX_DEPTH = 2 # A shallow depth is enough to test all stages

async def run_test_crawl():
    """
    Initializes and runs the WebCrawler asynchronously.
    """
    print("--- Test Execution Script Started ---")
    
    # 1. Initialize the crawler object
    try:
        crawler = WebCrawler(root_url=TEST_URL, max_depth=TEST_MAX_DEPTH)
    except ValueError as e:
        print(f"\n[FATAL ERROR] Initialization failed: {e}")
        return

    # 2. Run the three-stage crawl
    await crawler.run_crawler()
    
    print("--- Test Execution Script Finished ---")


if __name__ == '__main__':
    # Standard way to start an asyncio program
    try:
        asyncio.run(run_test_crawl())
    except KeyboardInterrupt:
        print("\nCrawl interrupted by user.")
    except Exception as e:
        print(f"\n[CRITICAL ERROR] An unhandled exception occurred: {e}")
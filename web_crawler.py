import asyncio
import re
import os
from pathlib import Path
from typing import Set, Tuple, List, Optional
from urllib.parse import urljoin, urlparse
from datetime import datetime

from playwright.async_api import async_playwright, Browser
import httpx 

# --- Configuration Constants (Module-Level) ---

# I. Configuration & Architecture
DEFAULT_START_URL = "https://www.scrapethissite.com/"
DEFAULT_MAX_DEPTH = 15 

# Output Management: Root directory for all results.
date_str = datetime.now().strftime("%Y_%m_%d")
OUTPUT_ROOT_DIR = Path(f"scraped_data_{date_str}")

# Timeout for network operations (seconds)
NETWORK_TIMEOUT = 30.0 

# --- File Extensions Classification ---

# 1. High-Value Documents/Data (Files we actively want to download in Stage 3)
# Includes documents and raw text for easy information extraction.
HIGH_VALUE_DATA_EXTENSIONS = (
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', # .txt added here
)

# 2. General Web Assets (Files we exclude from Stage 2 but do NOT download in Stage 3)
GENERAL_ASSET_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.svg', 
    '.zip', '.tar', '.gz', '.mp4', '.mp3', 
    '.css', '.js', '.ico', '.xml', # .txt removed here
)

# 3. The final combined list used by Stage 1 to prevent scraping (Stage 2)
# Any URL ending with these extensions will be routed to the 'files_to_download' list.
FILE_EXTENSIONS_TO_SAVE = HIGH_VALUE_DATA_EXTENSIONS + GENERAL_ASSET_EXTENSIONS 

# --- Utility Functions ---

def is_valid_url(url: str) -> bool:
    """
    Checks if a string is a valid, absolute HTTP or HTTPS URL.

    Input parameters:
    url (str): The URL string to validate.

    Output parameters:
    (bool): True if the URL is valid (has http/https scheme and network location), False otherwise.

    Example:
    >>> is_valid_url("https://example.com/page")
    True
    >>> is_valid_url("/relative/path")
    False
    """
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except ValueError:
        return False

def get_absolute_url(base_url: str, link: str) -> Optional[str]:
    """
    Converts a relative URL into an absolute URL, filtering out fragments and special schemes.

    Input parameters:
    base_url (str): The URL of the current page, used as the base for resolution (e.g., 'https://example.com/').
    link (str): The link found on the page (e.g., '/about' or 'page.html').

    Output parameters:
    (Optional[str]): The absolute, cleaned URL, or None if the link is invalid or uses a special scheme (mailto, tel, #fragment).

    Example:
    >>> get_absolute_url("https://example.com/page/", "../home.html")
    'https://example.com/home.html'
    >>> get_absolute_url("https://example.com/", "#section")
    None
    """
    if link.startswith(('#', 'mailto:', 'tel:')):
        return None
    
    absolute_url = urljoin(base_url, link)
    cleaned_url = absolute_url.split('#')[0]
    
    if is_valid_url(cleaned_url):
        return cleaned_url
    return None

def create_unique_filename_from_url(url: str, directory: Path, extension: str) -> Path:
    """
    Creates a unique, hierarchical filename for scraped content, handling potential conflicts.

    The naming convention uses the domain and URL path components, replaces unsafe characters 
    with underscores, and appends an incrementing counter if a file with the same name already exists.

    Input parameters:
    url (str): The URL to generate the filename for.
    directory (Path): The target directory where the file will be saved.
    extension (str): The file extension (e.g., '.html').

    Output parameters:
    (Path): The unique Path object that can be used to save the file without overwriting existing content.

    Example:
    >>> create_unique_filename_from_url("https://ex.com/a/b", Path("output/"), ".html")
    Path('output/ex_com_a_b.html') 
    """
    parsed_url = urlparse(url)
    
    # Use domain and path, replacing non-standard chars
    path_components = parsed_url.path.strip('/') or 'index'
    domain_prefix = parsed_url.netloc.replace('.', '_')
    
    # Replace anything non-alphanumeric/hyphen/underscore/dot with an underscore
    safe_path = re.sub(r'[^\w\-_\./]', '_', path_components)
    
    base_name = f"{domain_prefix}_{safe_path}"
    
    save_path = directory / f"{base_name}{extension}"
    counter = 0
    
    # Handle duplicate naming by appending a counter
    while save_path.exists():
        counter += 1
        save_path = directory / f"{base_name}_{counter}{extension}"
        
    return save_path

# --- Core Crawler Class ---

class WebCrawler:
    """
    A robust, three-stage asynchronous web crawler using Playwright and httpx, designed for 
    efficiency, persistence, and explicit memory management between stages.
    """
    
    def __init__(self, root_url: str = DEFAULT_START_URL, max_depth: int = DEFAULT_MAX_DEPTH):
        """
        Initializes the WebCrawler instance, setting up configuration and output directory structure.
        Performs initial URL validation.

        Input parameters:
        root_url (str): The starting URL for the crawl (defaults to DEFAULT_START_URL).
        max_depth (int): The maximum recursive depth for link following (default is 15).

        Output parameters:
        (None): Initializes the class attributes, creates necessary output directories, and raises a ValueError if the root_url is invalid.

        Example:
        >>> crawler = WebCrawler("https://test.com/", max_depth=2)
        """
        if not is_valid_url(root_url):
            raise ValueError(f"Invalid starting URL: {root_url}")

        self.root_url = root_url.rstrip('/')
        self.root_domain = urlparse(root_url).netloc
        self.max_depth = max_depth
        
        # II. Output Structure: Setup directories
        self.output_root = OUTPUT_ROOT_DIR
        self.discovery_dir = self.output_root / "discovery"
        self.content_dir = self.output_root / "content"
        self.files_dir = self.output_root / "files"
        
        # Ensure base directories are created
        self.discovery_dir.mkdir(parents=True, exist_ok=True)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory storage for Stage 1
        self.visited_urls: Set[str] = set()
        self.urls_to_scrape: Set[str] = set()
        self.files_to_download: Set[str] = set()

    
    # --- Persistence Handlers (Executed between stages) ---
    
    def _save_discovery_results(self):
        """
        Saves the discovered URLs (pages and files) stored in memory to disk. 
        This acts as the persistence checkpoint after Stage 1.

        Input parameters:
        (None) (Uses self.urls_to_scrape and self.files_to_download attributes)

        Output parameters:
        (None): Two text files (`urls_to_scrape.txt` and `files_to_download.txt`) are written to the 'discovery' directory.

        Example:
        # Assumes crawler is initialized and Stage 1 has populated the sets
        # crawler._save_discovery_results() 
        """
        # Save Scrape URLs
        scrape_path = self.discovery_dir / "urls_to_scrape.txt"
        with open(scrape_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(self.urls_to_scrape)))

        # Save File Download URLs
        file_path = self.discovery_dir / "files_to_download.txt"
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(self.files_to_download)))
        
        print(f"\n[PERSISTENCE] Discovery results saved to {self.discovery_dir}/...")

    def _load_urls_from_disk(self, filename: str) -> List[str]:
        """
        Loads a list of unique URLs from a persistence file in the discovery directory.

        Input parameters:
        filename (str): The name of the file to load (e.g., 'urls_to_scrape.txt').

        Output parameters:
        (List[str]): A list containing unique URLs read from the file. Returns an empty list if the file is not found.

        Example:
        # urls = crawler._load_urls_from_disk("urls_to_scrape.txt")
        # print(len(urls))
        """
        path = self.discovery_dir / filename
        if not path.exists():
            print(f"[ERROR] Persistence file not found: {path}")
            return []
            
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]

    # --- Core Stage 1: Discovery ---

    async def _stage_1_discover(self, browser: Browser, url: str, depth: int):
        """
        Recursively visits a page to find and collect all crawlable links and downloadable files.
        It respects the maximum depth and the root domain policy.

        Input parameters:
        browser (Browser): The Playwright Browser instance used to create new pages.
        url (str): The current URL to process.
        depth (int): The current crawl depth (0 is the root URL).

        Output parameters:
        (None): Populates the internal sets (self.visited_urls, self.urls_to_scrape, self.files_to_download) with discovered URLs.

        Example:
        # # Assumes browser is running
        # await crawler._stage_1_discover(browser, "https://start.com/", 0)
        """
        if depth > self.max_depth or url in self.visited_urls:
            return

        self.visited_urls.add(url)
        print(f"[{depth}/{self.max_depth}] Discovering: {url}")
        
        # Determine if the URL should be scraped (Stage 2) or downloaded (Stage 3)
        is_asset = url.lower().endswith(FILE_EXTENSIONS_TO_SAVE)
        
        if not is_asset:
            self.urls_to_scrape.add(url)
        
        page = None
        try:
            page = await browser.new_page()
            response = await page.goto(url, wait_until="domcontentloaded", timeout=NETWORK_TIMEOUT * 1000)
            
            if response and response.status >= 400:
                print(f"  [Error] HTTP {response.status} for {url}")
                return

            # Extract all href attributes
            hrefs = await page.evaluate('''() => 
                Array.from(document.querySelectorAll('[href]'))
                     .map(el => el.href).filter(href => href)
            ''')

            tasks = []
            for link in hrefs:
                absolute_url = get_absolute_url(url, link)
                
                if not absolute_url or absolute_url in self.visited_urls:
                    continue
                
                # Domain Policy Check
                if urlparse(absolute_url).netloc != self.root_domain:
                    self.visited_urls.add(absolute_url) 
                    continue

                # Check if the linked resource is a file extension (using the combined list)
                if absolute_url.lower().endswith(FILE_EXTENSIONS_TO_SAVE):
                    self.files_to_download.add(absolute_url)
                else:
                    # Recursively queue the next discovery step
                    tasks.append(
                        self._stage_1_discover(browser, absolute_url, depth + 1)
                    )
                        
            if tasks:
                await asyncio.gather(*tasks)

        except Exception as e:
            print(f"  [Exception] Failed to crawl {url}: {e}")
        finally:
            if page:
                await page.close()
                await asyncio.sleep(0.05) # Politeness delay

    # --- Core Stage 2: Extraction ---
    
    async def _stage_2_scrape_single(self, browser: Browser, url: str):
        """
        Scrapes the full HTML content of a single URL and saves it to the content directory.
        Includes a crucial check to ensure the URL returns HTML content before scraping.

        Input parameters:
        browser (Browser): The Playwright Browser instance.
        url (str): The URL to scrape.

        Output parameters:
        (None): Saves the full HTML content of the page to a uniquely named file in the 'content' directory.

        Example:
        # # Assumes browser is running
        # await crawler._stage_2_scrape_single(browser, "https://page.com/product/1")
        """
        page = None
        try:
            page = await browser.new_page()
            
            # FIX: Using wait_until="domcontentloaded" to prevent video/streaming timeouts
            response = await page.goto(url, wait_until="domcontentloaded", timeout=NETWORK_TIMEOUT * 1000)
            
            # --- CRITICAL STAGE 2 ROBUSTNESS CHECK ---
            content_type = response.headers.get('content-type', '').lower() if response else ''
            
            # Skip if Content-Type is clearly not HTML (e.g., text/css, application/json)
            if not ('text/html' in content_type or 'application/xhtml+xml' in content_type):
                print(f"  [Scrape Skip] Content Type is {content_type}. Skipping: {url}")
                return
            # --- END CRITICAL CHECK ---
            
            if response and response.status >= 400:
                print(f"  [Scrape Error] HTTP {response.status} for {url}")
                return
            
            html_content = await page.content()

            # Create unique filename based on URL path
            save_path = create_unique_filename_from_url(url, self.content_dir, ".html")
            
            # Ensure the parent directory exists before attempting to write the file
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Save the HTML content
            with open(save_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            print(f"  [SCRAPED] Content saved: {save_path.relative_to(self.output_root)}")

        except Exception as e:
            print(f"  [Scrape Exception] Failed to scrape {url}: {e}")
        finally:
            if page:
                await page.close()
                await asyncio.sleep(0.1) # Politeness delay

    # --- Core Stage 3: Download ---

    async def _stage_3_download_single(self, client: httpx.AsyncClient, url: str):
        """
        Performs a HEAD request validation to check status and content type, and if successful, 
        downloads the file content and handles filename duplication.

        Input parameters:
        client (httpx.AsyncClient): The asynchronous httpx client instance.
        url (str): The direct URL to the file.

        Output parameters:
        (None): Saves the binary file content to a uniquely named file in the 'files' directory. Skips the download if validation fails.

        Example:
        # # Assumes httpx client is initialized
        # await crawler._stage_3_download_single(client, "https://file.com/doc.pdf")
        """
        
        # 1. Validation using HEAD request (Robustness and Efficiency)
        try:
            # Setting a short timeout for the HEAD request since we only need headers
            head_response = await client.head(url, timeout=NETWORK_TIMEOUT)
            
            if head_response.status_code >= 400:
                print(f"  [FILE SKIP] Status {head_response.status_code} for {url}")
                return
            
            content_type = head_response.headers.get('Content-Type', '').lower()
            # If the header indicates HTML, it's a misleading link
            if 'text/html' in content_type:
                print(f"  [FILE SKIP] URL leads to an HTML page, not a binary file: {url}")
                return
                
        except Exception as e:
            print(f"  [FILE VALIDATION FAILED] {url}: {e}")
            return
            
        # 2. File Naming and Duplicate Handling
        
        filename = urlparse(url).path.split('/')[-1]
        if not filename:
            filename = 'downloaded_file_' + str(abs(hash(url)))
        
        save_path = self.files_dir / filename
        
        if save_path.exists():
            # Handle duplicates: Increment the filename counter
            base, ext = os.path.splitext(filename)
            counter = 1
            temp_path = self.files_dir / f"{base}_{counter}{ext}"
            while temp_path.exists():
                counter += 1
                temp_path = self.files_dir / f"{base}_{counter}{ext}"
            save_path = temp_path
            
        # 3. Download (GET request)
        try:
            print(f"  [DOWNLOD] Saving: {save_path.name}")
            # Use streaming to handle potentially large files without memory issues
            async with client.stream("GET", url, timeout=NETWORK_TIMEOUT) as response:
                response.raise_for_status() # Raise exception for bad status codes
                
                with open(save_path, 'wb') as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
            
            print(f"  [FILE SAVED] Saved to: {save_path.relative_to(self.output_root)}")

        except httpx.HTTPStatusError as e:
            print(f"  [DOWNLOAD ERROR] HTTP status {e.response.status_code} for {url}")
        except Exception as e:
            print(f"  [DOWNLOAD ERROR] Failed to download {url}: {e}")

    # --- Orchestration ---

    async def run_crawler(self):
        """
        The main public function to execute the three-stage crawl sequentially: 
        Discovery, Extraction, and Download. Manages the lifecycle of Playwright and 
        httpx clients and handles resource cleanup between stages.

        Input parameters:
        (None)

        Output parameters:
        (None): Executes the entire scraping process and prints status updates to the console.

        Example:
        # crawler = WebCrawler("https://example.com/", max_depth=1)
        # asyncio.run(crawler.run_crawler())
        """
        print(f"--- Starting Three-Stage Crawl for: {self.root_url} ---")
        print(f"Max Depth: {self.max_depth}. Output: {self.output_root.resolve()}")
        print("-" * 60)
        
        p = await async_playwright().start()
        
        # ----------------------------------------------------
        # --- STAGE 1: DISCOVERY (Crawl and Persist Links) ---
        # ----------------------------------------------------
        
        print("\n=== STAGE 1: DISCOVERY & PERSISTENCE ===")
        print("Starting deep link traversal...")
        
        browser = await p.chromium.launch(headless=True)
        try:
            await self._stage_1_discover(browser, self.root_url, depth=0)
        finally:
            # Cleanup 1: Close browser and free resources
            await browser.close()
        
        self._save_discovery_results()
        
        # Note: self.files_to_download now contains all types of file links
        print(f"STAGE 1 COMPLETE. Found {len(self.urls_to_scrape)} URLs and {len(self.files_to_download)} total file links.")
        self.visited_urls.clear() 
        
        # --------------------------------------------------
        # --- STAGE 2: EXTRACTION (Scraping Content) ---
        # --------------------------------------------------
        
        print("\n=== STAGE 2: EXTRACTION (Scraping Content) ===")
        
        urls_to_process = self._load_urls_from_disk("urls_to_scrape.txt")
        if not urls_to_process:
            print("No URLs found to scrape. Skipping Stage 2.")
        else:
            browser = await p.chromium.launch(headless=True)
            try:
                # Create concurrent scraping tasks
                scrape_tasks = [
                    asyncio.create_task(self._stage_2_scrape_single(browser, url))
                    for url in urls_to_process
                ]
                await asyncio.gather(*scrape_tasks)
            finally:
                # Cleanup 2: Close browser and free resources
                await browser.close()
                print("STAGE 2 COMPLETE. Playwright Browser resources released.")
        
        # ------------------------------------------------------
        # --- STAGE 3: DOWNLOAD (Saving High-Value Files) ---
        # ------------------------------------------------------

        print("\n=== STAGE 3: DOWNLOAD (Saving High-Value Document Files) ===")
        
        files_to_process = self._load_urls_from_disk("files_to_download.txt")
        
        # --- Apply the High-Value Document Filter ---
        high_value_files = [
            url for url in files_to_process 
            if url.lower().endswith(HIGH_VALUE_DATA_EXTENSIONS)
        ]
        
        if not high_value_files:
            print("No high-value document files found to download. Skipping Stage 3.")
        else:
            print(f"Processing {len(high_value_files)} high-value documents...")

            # Use httpx.AsyncClient for concurrent and efficient downloads/checks
            async with httpx.AsyncClient(timeout=NETWORK_TIMEOUT) as client:
                download_tasks = [
                    asyncio.create_task(self._stage_3_download_single(client, url))
                    for url in high_value_files
                ]
                await asyncio.gather(*download_tasks)
            
            print("STAGE 3 COMPLETE. File download tasks finished.")
            
        # ------------------------------------------------------
        # --- FINAL CLEANUP ---
        # ------------------------------------------------------
        
        await p.stop() # Final cleanup of the Playwright context
        print("-" * 60)
        print("Crawl and extraction process finished successfully.")
        print(f"Final output saved under: {self.output_root.resolve()}")
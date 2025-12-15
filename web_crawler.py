import asyncio
import re
import os
import time
from pathlib import Path
from typing import Set, Tuple, List, Optional
from urllib.parse import urljoin, urlparse
from datetime import datetime

from playwright.async_api import async_playwright, Browser, Download
import httpx 

# --- Configuration Constants (Module-Level) ---

# I. Configuration & Architecture
DEFAULT_START_URL = "https://www.scrapethissite.com/"
DEFAULT_MAX_DEPTH = 15 
DEFAULT_NETWORK_TIMEOUT = 30.0 

# Output Management: Root directory name prefix.
OUTPUT_ROOT_NAME = "scraped_data"

# --- File Extensions Classification ---

# 1. High-Value Documents/Data (Files we actively want to download in Stage 3)
HIGH_VALUE_DATA_EXTENSIONS = (
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt',
)

# 2. General Web Assets (Files we exclude from Stage 2 but do NOT download in Stage 3)
GENERAL_ASSET_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.svg', 
    '.zip', '.tar', '.gz', '.mp4', '.mp3', 
    '.css', '.js', '.ico', '.xml',
)

# 3. The final combined list used by Stage 1 to prevent scraping (Stage 2)
FILE_EXTENSIONS_TO_SAVE = HIGH_VALUE_DATA_EXTENSIONS + GENERAL_ASSET_EXTENSIONS 

# --- Utility Functions ---

def is_valid_url(url: str) -> bool:
    """
    Checks if a string is a valid, absolute HTTP or HTTPS URL.
    """
    try:
        result = urlparse(url)
        return all([result.scheme in ('http', 'https'), result.netloc])
    except ValueError:
        return False

def get_absolute_url(base_url: str, link: str) -> Optional[str]:
    """
    Converts a relative URL into an absolute URL, filtering out fragments and special schemes.
    """
    if link is None or link.startswith(('#', 'mailto:', 'tel:')):
        return None
    
    absolute_url = urljoin(base_url, link)
    cleaned_url = absolute_url.split('#')[0]
    
    if is_valid_url(cleaned_url):
        return cleaned_url
    return None

def create_unique_filename_from_url(url: str, directory: Path, extension: str) -> Path:
    """
    Creates a unique, hierarchical filename for scraped content, handling potential conflicts.
    """
    parsed_url = urlparse(url)
    
    path_components = parsed_url.path.strip('/') or 'index'
    domain_prefix = parsed_url.netloc.replace('.', '_')
    
    safe_path = re.sub(r'[^\w\-_\./]', '_', path_components)
    
    base_name = f"{domain_prefix}_{safe_path}"
    
    save_path = directory / f"{base_name}{extension}"
    counter = 0
    
    while save_path.exists():
        counter += 1
        save_path = directory / f"{base_name}_{counter}{extension}"
        
    return save_path

# --- Core Crawler Class ---

class WebCrawler:
    """
    A robust, three-stage asynchronous web crawler using Playwright and httpx, designed for 
    efficiency, persistence, dual-mode downloading, and full failure auditing.
    """
    HIGH_VALUE_DATA_EXTENSIONS = HIGH_VALUE_DATA_EXTENSIONS 
    
    def __init__(self, start_urls: List[str], max_depth: int = DEFAULT_MAX_DEPTH, network_timeout: float = DEFAULT_NETWORK_TIMEOUT):
        """
        Initializes the WebCrawler instance, setting up configuration and output directory structure.
        """
        if not start_urls or not all(is_valid_url(url) for url in start_urls):
            raise ValueError("Invalid or empty list of starting URLs provided.")

        self.start_urls = [url.rstrip('/') for url in start_urls]
        self.root_url = self.start_urls[0] 

        # Store a set of all allowed domains from the start URLs
        self.allowed_domains = {urlparse(url).netloc for url in self.start_urls}
        self.max_depth = max_depth
        self.network_timeout = network_timeout
        
        self.root_path_prefix = '/' 
        
        # II. Output Structure: Setup directories
        date_str_local = datetime.now().strftime("%Y_%m_%d")
        self.output_root = Path(f"{OUTPUT_ROOT_NAME}_{date_str_local}")

        self.discovery_dir = self.output_root / "discovery"
        self.content_dir = self.output_root / "content"
        self.files_dir = self.output_root / "files"
        # --- NEW: Rejection Auditing Directory ---
        self.rejections_dir = self.output_root / "rejections"
        
        # Ensure base directories are created
        self.discovery_dir.mkdir(parents=True, exist_ok=True)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.rejections_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory storage for Stage 1 (Successful Discovery)
        self.urls_to_scrape: Set[str] = set()
        self.files_to_download: Set[str] = set()
        self.visited_urls: Set[str] = set() 
        
        # --- NEW: In-memory storage for Audit/Rejections ---
        self.audit_download_rejections: Set[str] = set() # Skipped due to Content-Type (HTML)
        self.audit_download_failures: Set[str] = set()  # Failed due to 4xx/5xx/Exception
        self.audit_scrape_failures: Set[str] = set()    # Failed during Stage 2 scraping
        # ---------------------------------------------------

        # --- NEW: Concurrency & Rate Limiting ---
        self.discovery_sem = asyncio.Semaphore(10)   # limit concurrent discovery tasks
        self.scrape_sem = asyncio.Semaphore(5)       # limit concurrent scrape tasks
        self.download_sem = asyncio.Semaphore(5)     # limit concurrent downloads
        # Reduce rate limit slightly; large delays can look like freezes
        self.rate_limit_delay = 0.2                  # seconds between requests per domain
        self.domain_last_request: dict[str, float] = {}
        # Per-task safety timeout (seconds)
        self.task_timeout = max(5.0, self.network_timeout + 5.0)
        # --- NEW: Safety for large files ---
        self.max_file_size_bytes = 50 * 1024 * 1024  # 50 MB

    
    # --- NEW: URL Normalization & Rate Limiting Helpers ---

    def _normalize_url(self, url: str) -> str:
        """Normalize URL to reduce duplicates (strip fragments, trailing slash)."""
        parsed = urlparse(url)
        # strip fragment
        no_fragment = parsed._replace(fragment="").geturl()
        # strip trailing slash (except root path)
        if parsed.path != "/":
            no_fragment = no_fragment.rstrip("/")
        return no_fragment

    async def _respect_rate_limit(self, domain: str):
        """Ensure a minimum delay between requests per domain."""
        last = self.domain_last_request.get(domain, 0.0)
        now = time.monotonic()
        elapsed = now - last
        if elapsed < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - elapsed)
        self.domain_last_request[domain] = time.monotonic()

    # --- Persistence Handlers (Executed between stages) ---
    
    def _write_set_to_file(self, data_set: Set[str], filename: str, directory: Path):
        """Helper function to write a set of URLs to a specified file path."""
        file_path = directory / filename
        
        existing_data = set()
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = {line.strip() for line in f if line.strip()}
        
        all_data = existing_data.union(data_set)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(sorted(all_data)))


    def _save_discovery_results(self):
        """
        Saves all discovered (successful) and rejected/failed URLs to disk. 
        """
        # Save Scrape and File Download URLs (Successful Discovery)
        self._write_set_to_file(self.urls_to_scrape, "urls_to_scrape.txt", self.discovery_dir)
        self._write_set_to_file(self.files_to_download, "files_to_download.txt", self.discovery_dir)

        # --- NEW: Save Rejection/Failure Logs ---
        self._write_set_to_file(self.audit_download_rejections, "download_rejections.txt", self.rejections_dir)
        self._write_set_to_file(self.audit_download_failures, "download_failures.txt", self.rejections_dir)
        self._write_set_to_file(self.audit_scrape_failures, "scrape_failures.txt", self.rejections_dir)
        # ----------------------------------------
        
        print(f"\n[PERSISTENCE] Discovery results for the run saved to {self.discovery_dir}/...")
        print(f"[PERSISTENCE] Rejection/Failure logs saved to {self.rejections_dir}/...")

    def _load_urls_from_disk(self, filename: str) -> List[str]:
        """
        Loads a list of unique URLs from a persistence file in the discovery directory.
        """
        path = self.discovery_dir / filename
        if not path.exists():
            return []
            
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]

    # --- Core Stage 1: Discovery ---

    async def _stage_1_discover(self, browser: Browser, url: str, depth: int):
        """
        Recursively visits a page to find and collect all crawlable links and downloadable files.
        """
        # Normalize URL early
        url = self._normalize_url(url)
        if depth > self.max_depth or url in self.visited_urls:
            return

        self.visited_urls.add(url)
        print(f"[{depth}/{self.max_depth}] Discovering: {url}")
        
        is_asset = url.lower().endswith(FILE_EXTENSIONS_TO_SAVE)
        
        if not is_asset:
            self.urls_to_scrape.add(url)
        
        page = None
        try:
            async with self.discovery_sem:
                await self._respect_rate_limit(urlparse(url).netloc)

                page = await browser.new_page()
                # Avoid networkidle (can hang). Use domcontentloaded.
                response = await page.goto(url, wait_until="domcontentloaded", timeout=self.network_timeout * 1000)
                
                if response and response.status >= 400:
                    print(f"  [Error] HTTP {response.status} for {url}")
                    return

                # --- CRITICAL ENHANCED LINK EXTRACTION ---
                hrefs = await page.evaluate('''() => {
                    let links = [];
                    // 1. Standard hrefs 
                    document.querySelectorAll('[href]').forEach(el => links.push(el.href));
                    // 2. Links/URLs in data attributes
                    document.querySelectorAll('[data-url]').forEach(el => links.push(el.getAttribute('data-url')));
                    document.querySelectorAll('[data-href]').forEach(el => links.push(el.getAttribute('data-href')));
                    // 3. Links used in button clicks 
                    document.querySelectorAll('button[onclick]').forEach(el => {
                        const match = el.getAttribute('onclick').match(/["'](https?:\/\/[^"']+)["']/);
                        if (match) links.push(match[1]);
                    });
                    
                    return Array.from(new Set(links.filter(link => link && link.startsWith('http'))));
                }''')
                # --- END CRITICAL ENHANCED LINK EXTRACTION ---


                tasks = []
                for link in hrefs:
                    absolute_url = get_absolute_url(url, link)
                    if not absolute_url:
                        continue
                    absolute_url = self._normalize_url(absolute_url)

                    if absolute_url in self.visited_urls:
                        continue
                
                    parsed_link = urlparse(absolute_url)

                    # 1. Domain Policy Check 
                    if parsed_link.netloc not in self.allowed_domains:
                        self.visited_urls.add(absolute_url) 
                        continue
                
                    # Check if the linked resource is a file extension
                    if absolute_url.lower().endswith(FILE_EXTENSIONS_TO_SAVE):
                        self.files_to_download.add(absolute_url)
                    else:
                        # Wrap recursive calls with timeout to avoid deep hangs
                        tasks.append(asyncio.wait_for(
                            self._stage_1_discover(browser, absolute_url, depth + 1),
                            timeout=self.task_timeout
                        ))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            print(f"  [Exception] Failed to crawl {url}: {e}")
        finally:
            if page:
                await page.close()
                await asyncio.sleep(0.05) 

    # --- Core Stage 2: Extraction ---
    
    async def _stage_2_scrape_single(self, browser: Browser, url: str):
        """
        Scrapes the full HTML content of a single URL, logging failures to audit sets.
        """
        url = self._normalize_url(url)
        page = None
        try:
            async with self.scrape_sem:
                await self._respect_rate_limit(urlparse(url).netloc)

                page = await browser.new_page()
                # Use domcontentloaded to avoid hang; add bounded post-render wait
                response = await asyncio.wait_for(
                    page.goto(url, wait_until="domcontentloaded", timeout=self.network_timeout * 1000),
                    timeout=self.task_timeout
                )
                
                content_type = response.headers.get('content-type', '').lower() if response else ''
                
                # Skip if Content-Type is clearly not HTML (this is an *intentional* rejection)
                if not ('text/html' in content_type or 'application/xhtml+xml' in content_type):
                    print(f"  [Scrape Skip] Content Type is {content_type}. Skipping: {url}")
                    self.audit_scrape_failures.add(f"{url} | REASON: Non-HTML Content-Type: {content_type}")
                    return
                
                if response and response.status >= 400:
                    print(f"  [Scrape Error] HTTP {response.status} for {url}")
                    self.audit_scrape_failures.add(f"{url} | REASON: HTTP Error {response.status}")
                    return
                
                await page.wait_for_timeout(200) 
                html_content = await page.content()

                save_path = create_unique_filename_from_url(url, self.content_dir, ".html")
                
                save_path.parent.mkdir(parents=True, exist_ok=True)

                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                print(f"  [SCRAPED] Content saved: {save_path.relative_to(self.output_root)}")

        except asyncio.TimeoutError:
            print(f"  [Scrape Timeout] {url}")
            self.audit_scrape_failures.add(f"{url} | REASON: Scrape Timeout")
        except Exception as e:
            print(f"  [Scrape Exception] Failed to scrape {url}: {e}")
            self.audit_scrape_failures.add(f"{url} | REASON: Scrape Exception: {type(e).__name__}")
        finally:
            if page:
                await page.close()
                await asyncio.sleep(0.1) 

    # --- Core Stage 3: Download (Dual-Mode) ---

    async def _stage_3_playwright_download(self, browser: Browser, url: str):
        """
        Handles complex file downloads using Playwright's browser context (JavaScript required downloads).

        Returns: True if download was successful, False otherwise.
        """
        url = self._normalize_url(url)
        page = None
        try:
            async with self.download_sem:
                await self._respect_rate_limit(urlparse(url).netloc)

                context = await browser.new_context(accept_downloads=True)
                page = await context.new_page()

                # Do not block indefinitely waiting for a download
                try:
                    async with page.expect_download(timeout=int(self.network_timeout * 1000)) as download_info:
                        response = await page.goto(url, wait_until="load", timeout=self.network_timeout * 1000)
                        if response and response.status >= 400:
                            print(f"  [PLW ERROR] HTTP {response.status} for {url}")
                            self.audit_download_failures.add(f"{url} | REASON: PLW HTTP Error {response.status}")
                            return False
                    download = await asyncio.wait_for(download_info.value, timeout=self.task_timeout)
                except asyncio.TimeoutError:
                    print(f"  [PLW TIMEOUT] No download event for: {url}")
                    self.audit_download_failures.add(f"{url} | REASON: PLW Download Timeout")
                    return False

                suggested_filename = download.suggested_filename
                save_path = self.files_dir / suggested_filename
            
                if save_path.exists():
                    base, ext = os.path.splitext(suggested_filename)
                    counter = 1
                    temp_path = self.files_dir / f"{base}_{counter}{ext}"
                    while temp_path.exists():
                        counter += 1
                        temp_path = self.files_dir / f"{base}_{counter}{ext}"
                    save_path = temp_path

                await download.save_as(save_path)
            
                print(f"  [PLW SAVED] Downloaded {download.url} to: {save_path.relative_to(self.output_root)}")
                return True

        except Exception as e:
            print(f"  [PLW FAIL] Failed to download {url} via Playwright: {e}")
            self.audit_download_failures.add(f"{url} | REASON: PLW Exception: {type(e).__name__}")
            return False
        finally:
            if page:
                await page.close()

    async def _stage_3_download_single(self, client: httpx.AsyncClient, browser: Optional[Browser], url: str) -> bool:
        """
        Tries fast download via httpx.AsyncClient first. If validation fails (returns HTML), 
        it tries the robust Playwright method.
        
        Returns: True if download was successful (by either method), False otherwise.
        """
        url = self._normalize_url(url)

        # --- Attempt 1: Fast Download (httpx) ---
        try:
            async with self.download_sem:
                await self._respect_rate_limit(urlparse(url).netloc)

                head_response = await asyncio.wait_for(
                    client.head(url, timeout=self.network_timeout, follow_redirects=True),
                    timeout=self.task_timeout
                )
                
                if head_response.status_code >= 400:
                    print(f"  [HTTP SKIP] Status {head_response.status_code} for {url}")
                    self.audit_download_failures.add(f"{url} | REASON: HTTP Error {head_response.status_code}")
                    return False
                
                content_type = head_response.headers.get('Content-Type', '').lower()
                
                # Size guard from HEAD if provided
                content_length = head_response.headers.get('Content-Length')
                if content_length and int(content_length) > self.max_file_size_bytes:
                    print(f"  [SIZE SKIP] {url} exceeds max size ({content_length} bytes)")
                    self.audit_download_failures.add(f"{url} | REASON: Content-Length exceeds {self.max_file_size_bytes} bytes")
                    return False

                if 'text/html' in content_type or 'text/plain' in content_type:
                    print(f"  [HTTP REJECTION] Returned HTML ({content_type}). Trying Playwright: {url}")
                    self.audit_download_rejections.add(f"{url} | REASON: Content-Type HTML: {content_type}")
                    # Fall through to Playwright attempt below
                else:
                    # Determine filename: prefer Content-Disposition when present
                    filename = None
                    cd = head_response.headers.get('Content-Disposition', '')
                    match = re.search(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';]+)', cd, re.IGNORECASE)
                    if match:
                        filename = match.group(1)

                    if not filename:
                        filename = urlparse(url).path.split('/')[-1]
                        if head_response.history:
                            final_url_path = urlparse(str(head_response.url)).path
                            filename = final_url_path.split('/')[-1]
                        if not filename or '.' not in filename:
                            base_name = urlparse(url).netloc.replace('.', '_')
                            ext = os.path.splitext(url)[-1] or '.bin'
                            filename = f"downloaded_{base_name}_{abs(hash(urlparse(url).path))}{ext}"
                    
                    save_path = self.files_dir / filename
                    if save_path.exists():
                        base, ext = os.path.splitext(filename)
                        counter = 1
                        while (self.files_dir / f"{base}_{counter}{ext}").exists():
                            counter += 1
                        save_path = self.files_dir / f"{base}_{counter}{ext}"
                    
                    print(f"  [DOWNLOD] Saving: {save_path.name} (via httpx)")
                    async with client.stream("GET", url, timeout=self.network_timeout, follow_redirects=True) as response:
                        # Enforce overall streaming timeout to avoid stalls
                        response.raise_for_status()
                        total = 0
                        with open(save_path, 'wb') as f:
                            async for chunk in asyncio.wait_for(response.aiter_bytes(), timeout=self.task_timeout):
                                total += len(chunk)
                                if total > self.max_file_size_bytes:
                                    print(f"  [SIZE ABORT] {url} exceeded max stream size ({total} bytes)")
                                    self.audit_download_failures.add(f"{url} | REASON: Stream size exceeded {self.max_file_size_bytes} bytes")
                                    # Cleanup partial file
                                    try:
                                        f.close()
                                        save_path.unlink(missing_ok=True)
                                    except Exception:
                                        pass
                                    raise RuntimeError("Max file size exceeded during streaming")
                                f.write(chunk)
                    
                    print(f"  [HTTP SAVED] Saved to: {save_path.relative_to(self.output_root)}")
                    return True

        except asyncio.TimeoutError:
            print(f"  [HTTP TIMEOUT] {url}")
            self.audit_download_failures.add(f"{url} | REASON: HTTP Timeout")
        except Exception as e:
            print(f"  [HTTP ERROR] Failed with exception: {e}. Trying Playwright: {url}")
            self.audit_download_failures.add(f"{url} | REASON: HTTP Exception: {type(e).__name__}")
            # Fall through to Playwright attempt below

        # --- Attempt 2: Robust Download (Playwright) ---
        if browser:
            try:
                success = await asyncio.wait_for(self._stage_3_playwright_download(browser, url), timeout=self.task_timeout)
            except asyncio.TimeoutError:
                print(f"  [PLW TIMEOUT FALLBACK] {url}")
                self.audit_download_failures.add(f"{url} | REASON: PLW Fallback Timeout")
                success = False

            if success:
                rejection_entry_to_remove = next((entry for entry in self.audit_download_rejections if entry.startswith(url)), None)
                if rejection_entry_to_remove:
                    self.audit_download_rejections.discard(rejection_entry_to_remove)
                failure_entry_to_remove = next((entry for entry in self.audit_download_failures if entry.startswith(url)), None)
                if failure_entry_to_remove:
                    self.audit_download_failures.discard(failure_entry_to_remove)
                return True

        print(f"  [FAIL] Download failed both HTTP and Playwright attempts: {url}")
        return False

    # --- Orchestration ---

    async def run_crawler(self):
        """
        The main public function to execute the three-stage crawl sequentially (Discovery only).
        """
        print(f"--- Starting Multi-URL Crawl ---")
        print(f"Start URLs: {len(self.start_urls)}. Allowed Domains: {self.allowed_domains}")
        print(f"Max Depth: {self.max_depth}. Output: {self.output_root.resolve()}. Timeout: {self.network_timeout}s")
        print("-" * 60)
        
        p = await async_playwright().start()
        
        # ----------------------------------------------------
        # --- STAGE 1: DISCOVERY (Crawl and Persist Links) ---
        # ----------------------------------------------------
        
        print("\n=== STAGE 1: DISCOVERY & PERSISTENCE ===")
        
        browser = await p.chromium.launch(headless=True) 
        try:
            # Create concurrent discovery tasks for all start URLs
            discovery_tasks = [
                asyncio.wait_for(self._stage_1_discover(browser, url, depth=0), timeout=self.task_timeout)
                for url in self.start_urls
            ]
            await asyncio.gather(*discovery_tasks, return_exceptions=True)
        finally:
            await browser.close()
        
        # Persistence step: Writes discovered links and audit logs to disk 
        self._save_discovery_results() # This saves the clean discovery lists AND empty audit sets (for now)
        
        print(f"STAGE 1 COMPLETE. Discovered {len(self.urls_to_scrape)} URLs and {len(self.files_to_download)} files across all start points.")
        self.visited_urls.clear() 
        
        await p.stop() 
        print("Playwright resources released after Discovery.")
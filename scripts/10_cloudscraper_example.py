import cloudscraper

def main():
    scraper = cloudscraper.create_scraper()
    r = scraper.get("https://httpbin.org/get")
    print("status:", r.status_code)
    print("json keys:", list(r.json().keys()))

if __name__ == "__main__":
    main()

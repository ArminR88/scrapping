import requests
from fake_useragent import UserAgent

def main():
    ua = UserAgent()
    headers = {"User-Agent": ua.chrome}
    r = requests.get("https://httpbin.org/headers", headers=headers)
    print("used UA:", headers["User-Agent"])
    print("response headers snippet:", r.json().get("headers"))

if __name__ == "__main__":
    main()

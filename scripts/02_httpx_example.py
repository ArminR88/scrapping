import httpx

def main():
    resp = httpx.get("https://httpbin.org/get", params={"q": "httpx"})
    print("status:", resp.status_code)
    print("headers sample:", dict(list(resp.headers.items())[:3]))

if __name__ == "__main__":
    main()

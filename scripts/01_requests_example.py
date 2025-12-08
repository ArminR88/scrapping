import requests

def main():
    resp = requests.get("https://httpbin.org/get", params={"q": "test"})
    print("status:", resp.status_code)
    print("json keys:", list(resp.json().keys()))

if __name__ == "__main__":
    main()

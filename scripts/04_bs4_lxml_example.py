import requests
from bs4 import BeautifulSoup

def main():
    r = requests.get("https://example.com")
    soup = BeautifulSoup(r.text, "lxml")
    print("title:", soup.title.string.strip())

if __name__ == "__main__":
    main()

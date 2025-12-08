import requests
from parsel import Selector

def main():
    r = requests.get("https://example.com")
    sel = Selector(text=r.text)
    h1 = sel.css("h1::text").get()
    print("h1:", h1)

if __name__ == "__main__":
    main()

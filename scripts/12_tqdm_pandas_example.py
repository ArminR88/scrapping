import requests
from tqdm import tqdm
import pandas as pd

URLS = [f"https://httpbin.org/get?i={i}" for i in range(5)]

def main():
    rows = []
    for u in tqdm(URLS, desc="fetching"):
        r = requests.get(u)
        rows.append({"url": u, "status": r.status_code})
    df = pd.DataFrame(rows)
    print(df)

if __name__ == "__main__":
    main()

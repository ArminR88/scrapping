import asyncio
import aiohttp

URLS = ["https://httpbin.org/delay/1", "https://httpbin.org/get", "https://example.com"]

async def fetch(session, url):
    async with session.get(url) as r:
        return url, r.status

async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, u) for u in URLS]
        results = await asyncio.gather(*tasks)
        for url, status in results:
            print(url, "->", status)

if __name__ == "__main__":
    asyncio.run(main())

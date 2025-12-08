import scrapy

class SimpleSpider(scrapy.Spider):
    name = "simple"
    start_urls = ["https://httpbin.org/html"]

    def parse(self, response):
        title = response.css("h1::text").get()
        yield {"url": response.url, "title": title}

# Run: scrapy runspider scripts/06_scrapy_basic_spider.py -o out.json

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def main():
    opts = Options()
    opts.add_argument("--headless=new")  # or "--headless"
    opts.add_argument("--no-sandbox")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    try:
        driver.get("https://example.com")
        print("title:", driver.title)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import re

options = Options()
options.add_argument("--window-size=1200,800")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)
driver = webdriver.Chrome(options=options)

driver.get("https://wellfound.com/jobs?keywords=Product+Management+Intern")
time.sleep(10) # 10s to let user login manually or load page

print("Title:", driver.title)
print("Looking for links on the page...")

links = driver.find_elements(By.TAG_NAME, "a")
print(f"Total links: {len(links)}")

job_url_pattern = re.compile(
    r"wellfound\.com/(jobs/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+"
    r"|company/[a-zA-Z0-9_-]+/jobs/[a-zA-Z0-9_-]+)"
)

for el in links:
    href = el.get_attribute("href") or ""
    if "/job/" in href or "/jobs/" in href or "/company/" in href:
        print(f"Potential job link: {href}")
        if job_url_pattern.search(href):
            print("  --> Match!")

driver.quit()

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument("--window-size=1200,800")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

driver = webdriver.Chrome(options=options)
driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

print("Navigating to Wellfound login...")
driver.get("https://wellfound.com/login")
time.sleep(8)

print("Title:", driver.title)
print("Current URL:", driver.current_url)

inputs = driver.find_elements(By.TAG_NAME, "input")
print(f"Found {len(inputs)} inputs:")
for inp in inputs:
    try:
        html = inp.get_attribute('outerHTML')
        print("  -", html)
    except:
        pass

buttons = driver.find_elements(By.TAG_NAME, "button")
print(f"Found {len(buttons)} buttons:")
for btn in buttons:
    try:
        html = btn.get_attribute('outerHTML')
        text = btn.text
        if "log" in text.lower() or "submit" in text.lower() or "sign" in text.lower():
            print("  -", text, html)
    except:
        pass

driver.quit()

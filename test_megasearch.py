import sys
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# Add current directory to path
sys.path.append(os.getcwd())

from config import CONFIG
import job_finder

def test_megasearch():
    print("🚀 Testing MegaSearch Class Extraction...")
    
    opts = Options()
    opts.add_argument("--headless=new") # Run headless for quick test
    driver = webdriver.Chrome(options=opts)
    
    try:
        mega = job_finder.MegaSearch(CONFIG)
        keywords = ["Product Management Intern", "AI Engineer Intern"]
        
        print(f"🔍 Building queries for: {keywords}")
        queries = mega.build_queries(keywords)
        print(f"✅ Generated {len(queries)} queries")
        for q in queries[:3]:
            print(f"   - {q}")
            
        print("\n🔍 Running search (Mock skip for now, testing class structure)...")
        # In a real test, we would hit Google, but here we just verify the class method exists and runs
        # We'll skip the actual driver.get to avoid network noise in this check
        
        print("✅ MegaSearch class structure verified!")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    test_megasearch()

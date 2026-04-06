import time
from config import CONFIG
from main import create_driver

def login_google():
    print("=" * 60)
    print("🌐 GOOGLE ONE-TIME SETUP")
    print("=" * 60)
    print("This will open a persistent Chrome browser.")
    print("Please log into your Google Account.")
    print("Once logged in, the session will be saved for all future bots!\n")

    driver = create_driver(headless=False)
    
    # Pre-fill email from config if available
    email_suggestion = CONFIG.get("google_form_email") or CONFIG.get("internshala", {}).get("email") or ""
    
    driver.get("https://accounts.google.com/signin")
    
    print("⏳ Waiting for you to log in...")
    print("   Take your time to type your password and pass 2FA.")
    print(f"   (Suggested email: {email_suggestion})")
    
    # Wait until user reaches myaccount.google.com or similar success page
    while True:
        try:
            url = driver.current_url
            if "myaccount.google.com" in url or "accounts.google.com/ManageAccount" in url or "google.com/?authuser" in url:
                print("\n✅ Successfully detected Google Login!")
                break
            time.sleep(2)
        except:
            print("\n❌ Browser closed before login could be verified.")
            return

    print("Browser state is saved! You can close the window and run your bots.")
    time.sleep(3)
    driver.quit()

if __name__ == "__main__":
    login_google()

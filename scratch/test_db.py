import sys
import os
import uuid

# Add current directory and backend to path
sys.path.insert(0, os.getcwd())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.config import settings
from backend.models.user import User
from backend.models.profile import UserProfile

def test_db_types():
    url = settings.database_url.replace("sqlite+aiosqlite", "sqlite").replace(
        "postgresql+asyncpg", "postgresql+psycopg2"
    )
    print(f"Connecting to: {url}")
    engine = create_engine(url, connect_args={"check_same_thread": False} if "sqlite" in url else {})
    Session = sessionmaker(bind=engine)
    session = Session()

    profile = session.query(UserProfile).first()
    if profile:
        print(f"Type of profile.job_preferences: {type(profile.job_preferences)}")
        print(f"Value: {profile.job_preferences}")
        print(f"Type of profile.platform_passwords: {type(profile.platform_passwords)}")
        
        if isinstance(profile.job_preferences, str):
            print("ERROR DETECTED: JSON column loaded as string!")
    else:
        print("No profile found.")
    session.close()

if __name__ == "__main__":
    test_db_types()

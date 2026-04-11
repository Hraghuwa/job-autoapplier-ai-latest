import json
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, String, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(String, primary_key=True)
    user_id = Column(String)
    job_preferences = Column(JSON) # Using JSON instead of JSONB for SQLite test
    platform_passwords = Column(JSON)

def test_type():
    db_path = "/tmp/jadb/jobagent.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    session = Session()

    user_id = "42641418-6dfa-4b27-b902-6d31021c81bd"
    # Note: query by string user_id since my mock model uses String
    from sqlalchemy import text
    result = session.execute(text("SELECT job_preferences, platform_passwords FROM user_profiles WHERE user_id = :uid"), {"uid": user_id.replace("-", "")}).fetchone()
    
    if result:
        print(f"Raw job_preferences type: {type(result[0])}")
        print(f"Raw platform_passwords type: {type(result[1])}")
        print(f"Raw job_preferences: {result[0][:50]}...")
    else:
        print("No profile found")
    
    session.close()

if __name__ == "__main__":
    test_type()

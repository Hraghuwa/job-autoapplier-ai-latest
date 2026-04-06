import asyncio
import uuid
from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models.user import User
from backend.models.profile import UserProfile
from backend.services.crypto_service import encrypt

async def update_user():
    email = "hraghuwanshi3110@gmail.com" # Found in previous run
    target_job = "product manager intern paid"
    linkedin_pass = "Password1!"
    
    async with AsyncSessionLocal() as db:
        # Find user
        r = await db.execute(select(User).where(User.email == email))
        user = r.scalar_one_or_none()
        
        if not user:
            r = await db.execute(select(User).limit(1))
            user = r.scalar_one_or_none()
            if not user:
                print("No user found in database.")
                return

        print(f"Updating user: {user.email} (ID: {user.id})")
        
        # Update Profile
        r = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        profile = r.scalar_one_or_none()
        
        if profile:
            # 1. Update job preferences
            job_prefs = dict(profile.job_preferences or {})
            job_prefs["job_titles"] = [target_job]
            profile.job_preferences = job_prefs
            
            # 2. Update platform passwords
            passwords = dict(profile.platform_passwords or {})
            passwords["linkedin"] = encrypt(linkedin_pass)
            profile.platform_passwords = passwords
            
            print(f"Updated platform_passwords for linkedin and set job_titles to '{target_job}'.")
        else:
            print("Profile not found for user.")

        await db.commit()
        print("Changes committed successfully.")

if __name__ == "__main__":
    asyncio.run(update_user())

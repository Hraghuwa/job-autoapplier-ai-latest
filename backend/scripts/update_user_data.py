"""Set a user's target job title and LinkedIn password (dev helper).

    python -m backend.scripts.update_user_data <email> "<target job>"

The password is prompted for, never passed on the command line or stored here.
"""
import asyncio
import getpass
import sys

from sqlalchemy import select
from backend.database import AsyncSessionLocal
from backend.models.user import User
from backend.models.profile import UserProfile
from backend.services.crypto_service import encrypt


async def update_user(email: str, target_job: str, linkedin_pass: str):
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(User).where(User.email == email))
        user = r.scalar_one_or_none()
        if not user:
            # No fallback to "some other user" — that would overwrite a stranger's password.
            print(f"No user with email {email}.")
            return

        print(f"Updating user: {user.email} (ID: {user.id})")
        r = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
        profile = r.scalar_one_or_none()
        if not profile:
            print("Profile not found for user.")
            return

        job_prefs = dict(profile.job_preferences or {})
        job_prefs["job_titles"] = [target_job]
        profile.job_preferences = job_prefs

        passwords = dict(profile.platform_passwords or {})
        passwords["linkedin"] = encrypt(linkedin_pass)
        profile.platform_passwords = passwords

        await db.commit()
        print(f"Updated linkedin password and set job_titles to '{target_job}'.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    asyncio.run(update_user(sys.argv[1], sys.argv[2], getpass.getpass("LinkedIn password: ")))

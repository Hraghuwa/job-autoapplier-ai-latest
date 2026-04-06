"""
Seed script — creates/updates the admin account with pre-loaded profile data
from agents/config.py.

Usage:
    source .venv/bin/activate
    python seed_admin.py
"""
import asyncio
import sys
import os
import uuid
import secrets
import json

sys.path.insert(0, os.path.dirname(__file__))

# --- Credentials for the admin web account ---
ADMIN_EMAIL    = "hraghuwanshi3110@gmail.com"
ADMIN_PASSWORD = "admin"          # change after first login if desired
ADMIN_NAME     = "Harsh Raghuwanshi"

async def main():
    from backend.config import settings
    from backend.database import engine, Base, AsyncSessionLocal
    from backend.models.user import User, PlanEnum
    from backend.models.profile import UserProfile
    from backend.models.referral import Referral
    from passlib.context import CryptContext
    from sqlalchemy import select
    from cryptography.fernet import Fernet

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    # Fernet for encrypting stored credentials
    try:
        fernet = Fernet(settings.fernet_key.encode())
        def enc(v): return fernet.encrypt(v.encode()).decode()
    except Exception:
        def enc(v): return v   # fallback — store plaintext if key broken

    # ── Ensure tables exist ────────────────────────────────────────────────────
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # ── 1. Upsert user ────────────────────────────────────────────────────
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                id=uuid.uuid4(),
                email=ADMIN_EMAIL,
                name=ADMIN_NAME,
                hashed_password=pwd_ctx.hash(ADMIN_PASSWORD),
                plan=PlanEnum.pro,
                is_admin=True,
            )
            db.add(user)
            print(f"✅ Created user: {ADMIN_EMAIL}")
        else:
            user.hashed_password = pwd_ctx.hash(ADMIN_PASSWORD)
            user.plan = PlanEnum.pro
            user.is_admin = True
            user.name = ADMIN_NAME
            print(f"🔄 Updated existing user: {ADMIN_EMAIL}")

        await db.flush()

        # ── 2. Referral code (if not exists) ──────────────────────────────────
        ref_result = await db.execute(
            select(Referral).where(Referral.referrer_id == user.id)
        )
        if not ref_result.scalar_one_or_none():
            ref_code = secrets.token_urlsafe(10)[:12].upper()
            db.add(Referral(id=uuid.uuid4(), referrer_id=user.id, code=ref_code))
            print(f"✅ Referral code created: {ref_code}")

        # ── 3. Upsert profile ─────────────────────────────────────────────────
        prof_result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        profile = prof_result.scalar_one_or_none()
        if profile is None:
            profile = UserProfile(id=uuid.uuid4(), user_id=user.id)
            db.add(profile)
            print("✅ Created profile")
        else:
            print("🔄 Updated existing profile")

        # ── 4. Job preferences from config ────────────────────────────────────
        profile.job_preferences = {
            "job_titles": [
                "Product Management Intern", "Project Management Intern",
                "GTM Intern", "Founders Office Intern",
                "Business Analyst Intern", "Business Strategist Intern",
                "Tech Consultant Intern", "AI Management Intern",
                "Management Consulting Intern", "Program Manager Intern",
                "Strategy Intern", "Growth Intern",
            ],
            "locations": ["India", "Remote"],
            "remote": True,
            "employment_types": ["internship"],
            "max_jobs_per_day": 100,
            "recently_posted": True,
        }

        # ── 5. Autofill bank from config["profile"] ───────────────────────────
        profile.autofill_bank = {
            "full_name": "Harsh Raghuwanshi",
            "first_name": "Harsh",
            "last_name": "Raghuwanshi",
            "name": "Harsh Raghuwanshi",
            "gender": "Male",
            "age": "24",
            "phone": "8109580642",
            "mobile": "8109580642",
            "email": "hraghu3110@outlook.com",
            "alt_email": "harsh2.tapmiblr2025@learner.manipal.edu",
            "city": "Bangalore",
            "location": "Bangalore",
            "country": "India",
            "linkedin_url": "https://www.linkedin.com/in/harsh-raghuwanshi-570868359/",
            "portfolio_url": "https://harshraghuwanshi.figma.site",
            "personal_website": "https://harshraghuwanshi.figma.site",
            "degree": "MBA",
            "branch": "Technology Management",
            "university": "Manipal/T.A Pai Management Institute",
            "college": "Manipal/T.A Pai Management Institute",
            "graduation_year": "2027",
            "tenth_marks": "85",
            "twelfth_marks": "78",
            "grad_cgpa": "7.80",
            "mba_cgpa": "6.97",
            "cgpa": "7.80",
            "percentage": "78",
            "previous_degree": "BA Programme (Political Science & Computer Applications)",
            "previous_university": "University of Delhi",
            "previous_cgpa": "7.80",
            "years_experience": "4",
            "years_of_experience": "4",
            "current_company": "Apna Supermarket",
            "current_role": "Cofounder",
            "internship_duration": "3 months",
            "availability": "01/04/2026",
            "join_date": "01/04/2026",
            "notice_period": "20",
            "expected_salary": "40000",
            "expected_stipend": "40000",
            "current_stipend": "80000",
            "previous_salary": "80000",
            "current_ctc": "80000",
            "willing_to_relocate": "Yes",
            "has_laptop": "Yes",
            "has_product_ai_experience": "Yes",
            "tools_used": "Google AI Studio, Anti Gravity, Replit, Gemini, Claude",
            "skills": "Product Management, Product Roadmapping, Requirements Gathering, Story Mapping, Design Thinking, Market Research, Data Analysis, Python, SQL, Power BI, Figma, ERP, CRM, AI Tools (Gemini, Claude), n8n, Shopify, GTM Strategy",
            "tools": "Google AI Studio, Anti Gravity, Replit, Gemini, Claude, Figma, Python, SQL, Power BI, n8n",
            "certifications": "IBM AI Product Manager, Stanford IoT Fundamentals, AWS Cloud Practitioner (Pursuing), Finlatics Generative AI Programme",
            "work_authorization": "Yes",
            "require_sponsorship": "No",
            "legally_authorized": "Yes",
            "heard_about_us": "LinkedIn",
            "rag_explanation": "Sourcing information directly from the origin eliminates hallucinations.",
        }

        # ── 6. Cover letter ───────────────────────────────────────────────────
        profile.cover_letter = """I am Harsh Raghuwanshi, currently pursuing MBA TECH at TAPMI Bengaluru (2025-2027).
I am very excited to apply for this internship opportunity.

I bring 4+ years of hands-on entrepreneurial experience as Co-founder of Apna Supermarket,
where I led product management, GTM strategy, and growth initiatives — achieving 25% annual
revenue growth and scaling turnover to approximately ₹2.5 Cr. I have strong experience in
product roadmapping, requirements gathering, story mapping, design thinking, and agile
methodologies.

I am skilled in ERP, CRM, AI tools (Gemini, Claude, n8n), Figma, Power BI, SQL, and Python.
I hold an IBM AI Product Manager certification and have built AI-driven products including
chatbots and automation systems.

My background in product lifecycle management, market research, data-driven decision making,
and cross-functional team leadership makes me a strong fit for this role.

I am eager to contribute meaningfully to your organization during the 3-month internship period.

Warm regards,
Harsh Raghuwanshi
MBA TECH | TAPMI Bengaluru
8109580642 | harsh2.tapmiblr2025@learner.manipal.edu"""

        # ── 7. Extracted resume data (for match scoring) ──────────────────────
        profile.extracted_data = {
            "name": "Harsh Raghuwanshi",
            "email": "harsh2.tapmiblr2025@learner.manipal.edu",
            "phone": "8109580642",
            "skills": [
                "Product Management", "Product Roadmapping", "Requirements Gathering",
                "Story Mapping", "Design Thinking", "Market Research", "Data Analysis",
                "Python", "SQL", "Power BI", "Figma", "ERP", "CRM",
                "Gemini", "Claude", "n8n", "Shopify", "GTM Strategy",
                "Agile", "Scrum", "Business Analysis",
            ],
            "education": [
                {"degree": "MBA TECH", "institution": "TAPMI Bengaluru", "year": "2027"},
                {"degree": "BA Programme", "institution": "University of Delhi", "year": "2024", "cgpa": "7.80"},
            ],
            "experience": [
                {
                    "role": "Co-founder",
                    "company": "Apna Supermarket",
                    "duration": "4 years",
                    "highlights": [
                        "Led product management and GTM strategy",
                        "25% annual revenue growth",
                        "Scaled turnover to ₹2.5 Cr",
                    ],
                }
            ],
            "certifications": [
                "IBM AI Product Manager",
                "Stanford IoT Fundamentals",
                "Finlatics Generative AI Programme",
            ],
            "summary": "MBA TECH student at TAPMI Bengaluru with 4+ years entrepreneurial experience in product management, GTM strategy, and business operations.",
        }

        # ── 8. Platform credentials (Fernet-encrypted) ────────────────────────
        profile.platform_passwords = {
            "linkedin":     {"email": enc("hraghuwanshi3110@gmail.com"), "password": enc("Harsh@420")},
            "wellfound":    {"email": enc("hraghu3110@outlook.com"),    "password": enc("Harsh@rag7710")},
            "internshala":  {"email": enc("hraghuwanshi59@gmail.com"),  "password": enc("YOUR_INTERNSHALA_PASSWORD")},
        }

        # ── 9. Gemini key on the user row ────────────────────────────────────
        user.gemini_key_encrypted = enc("AIzaSyAfN5DAZhXhEkSDHEs4JzmWHi5QwLnXtz8")

        await db.commit()

    print()
    print("=" * 50)
    print("🎉 Admin account ready!")
    print(f"   URL:      http://localhost:3000/login")
    print(f"   Email:    {ADMIN_EMAIL}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print(f"   Plan:     PRO  (full access)")
    print(f"   Admin:    YES")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())

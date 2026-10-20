# ============================================================
#  ✏️  FILL IN YOUR DETAILS HERE BEFORE RUNNING
#  (This file is the CLI/standalone fallback config.
#   When running via the web app, all values are loaded from
#   the database — you do NOT need to edit this file.)
# ============================================================

CONFIG = {
    # ──────────────────────────────────────────
    #  GEMINI AI API KEY
    # ──────────────────────────────────────────
    "gemini_api_key": "",   # Add your Gemini API key from https://aistudio.google.com/

    # ──────────────────────────────────────────
    #  YOUR DETAILS
    # ──────────────────────────────────────────
    "name": "",             # Your full name
    "phone": "",            # Your phone number
    "email": "",            # Your primary email

    # --- Resume Path ---
    # Full path to your resume PDF, e.g. "/Users/you/Downloads/resume.pdf"
    "resume_path": "",

    # --- Platform Credentials ---
    "linkedin": {
        "email": "",
        "password": "",
    },
    "internshala": {
        "email": "",
        "password": "",
    },
    "unstop": {
        "email": "",
        "password": "",
    },
    "naukri": {
        "email": "",
        "password": "",
    },
    "wellfound": {
        "email": "",
        "password": "",
    },

    # ──────────────────────────────────────────
    # --- Job Preferences (edit to match your targets) ---
    # ──────────────────────────────────────────
    "keywords": [
        "Product Management Intern",
        "Project Management Intern",
        "GTM Intern",
        "Founders Office Intern",
        "Business Analyst Intern",
        "Business Strategist Intern",
        "Tech Consultant Intern",
        "AI Management Intern",
        "Management Consulting Intern",
        "Program Manager Intern",
        "Strategy Intern",
        "Growth Intern",
    ],

    "locations": [
        "India",
        "Remote",
    ],

    "recently_posted": True,

    # ──────────────────────────────────────────
    # --- Role Agents (parallel search buckets) ---
    # ──────────────────────────────────────────
    "role_agents": [
        {
            "name": "AI & Management",
            "emoji": "🧠",
            "keywords": [
                "Product Management Intern",
                "Project Management Intern",
                "GTM Intern",
                "Tech Consulting Intern",
                "AI Management Intern",
                "Founder Office Intern",
                "Business Strategist Intern",
                "Management Consulting Intern",
                "Program Manager Intern",
            ],
        },
        {
            "name": "Founder Office",
            "emoji": "🏢",
            "keywords": [
                "Founder Office Intern",
                "Founders Office Intern",
                "CEO Office Intern",
                "Chief of Staff Intern",
                "Founder Office Associate",
            ],
        },
        {
            "name": "Business Strategy",
            "emoji": "📊",
            "keywords": [
                "Business Strategist Intern",
                "Business Strategy Intern",
                "Strategy Intern",
                "Strategy Consulting Intern",
            ],
        },
        {
            "name": "Business Analyst",
            "emoji": "📈",
            "keywords": [
                "Business Analyst Intern",
                "Data Analyst Intern",
                "Product Analyst Intern",
            ],
        },
        {
            "name": "Tech Consulting",
            "emoji": "🧑‍💼",
            "keywords": [
                "Tech Consultant Intern",
                "Technology Consultant Intern",
                "IT Consulting Intern",
                "Management Consultant Intern",
            ],
        },
        {
            "name": "Operations",
            "emoji": "⚙️",
            "keywords": [
                "Operations Intern",
                "Operations Management Intern",
                "Business Operations Intern",
                "Operations Associate",
            ],
        },
        {
            "name": "General Management",
            "emoji": "📋",
            "keywords": [
                "Management Trainee",
                "Management Intern",
                "Growth Intern",
                "GTM Intern",
                "Product Management Intern",
                "Program Manager Intern",
                "Project Manager Intern",
                "Project Management Intern",
            ],
        },
    ],

    # --- Cover Letter template ---
    # Replace with YOUR background. The web app generates this from your
    # uploaded resume + job description automatically. This is only the
    # CLI standalone fallback.
    "cover_letter": """
Hi, I'm [YOUR NAME]. I'm excited about this opportunity and believe my background in
[YOUR FIELD / EXPERIENCE] makes me a strong fit.

I bring [X] years of experience in [SKILLS / ROLES]. I am skilled in [TOOLS / TECH].

I look forward to contributing meaningfully to your organization.

Warm regards,
[YOUR NAME]
[YOUR PHONE] | [YOUR EMAIL]
""".strip(),

    # --- Profile for smart form filling ---
    # Fill these with your real details. Web-app users: leave blank —
    # the app reads these from your saved profile in the database.
    "profile": {
        "full_name": "",
        "first_name": "",
        "last_name": "",
        "gender": "",
        "age": "",
        "phone": "",
        "email": "",
        "city": "",
        "location": "",
        "country": "India",
        "linkedin": "",
        "personal_website": "",

        # Education
        "degree": "",
        "course": "",
        "branch": "",
        "university": "",
        "college": "",
        "graduation_year": "",
        "cgpa": "",
        "percentage": "",

        # Experience
        "years_experience": "",
        "current_company": "",
        "current_role": "",
        "internship_duration": "3 months",
        "availability": "",
        "join_date": "",
        "notice_period": "",
        "expected_salary": "",
        "current_ctc": "",
        "willing_to_relocate": "Yes",
        "has_laptop": "Yes",

        # Skills & certifications
        "skills": "",
        "tools_used": "",
        "certifications": "",

        # Standard answers
        "work_authorization": "Yes",
        "require_sponsorship": "No",
        "legally_authorized": "Yes",
        "heard_about_us": "LinkedIn",
    },

    # ──────────────────────────────────────────
    # --- Web Search / Company Career Pages ---
    # ──────────────────────────────────────────
    "web_search": {
        "enabled": True,
        "max_results_per_query": 15,
        "tab_limit": 50,    # How many job tabs to open per run (20/50/70/100)
        "target_companies": [
            # Big Tech
            "google", "microsoft", "amazon", "apple", "meta",
            "atlassian", "adobe", "salesforce", "sap", "oracle",
            "notion", "stripe", "twilio", "databricks", "snowflake",
            # Indian Unicorns & Startups
            "flipkart", "razorpay", "cred", "meesho", "swiggy",
            "zomato", "paytm", "phonepe", "groww", "zerodha",
            "freshworks", "zoho", "ola", "myntra", "nykaa",
            "unacademy", "byju", "upgrad", "sharechat", "dream11",
            "slice", "jupiter", "bharatpe", "lenskart", "boat",
            "mamaearth", "rapido", "urbancompany", "curefit",
            "indmoney", "smallcase", "dunzo", "spinny", "cars24",
            "delhivery", "shiprocket", "cleartax", "chargebee",
            "postman", "browserstack", "hasura",
            "vedantu", "physicswallah", "scaler", "interviewbit",
            # Consulting
            "bcg", "mckinsey", "bain", "accenture", "deloitte",
            "kpmg", "ey", "pwc", "capgemini", "wipro",
            "tcs", "infosys", "cognizant", "hcl",
            # Others
            "uber", "grab", "airbnb", "netflix",
        ],
        "ats_domains": [
            "lever.co", "greenhouse.io", "workday.com",
            "smartrecruiters.com", "icims.com", "ashbyhq.com",
            "breezy.hr", "bamboohr.com", "recruitee.com",
            "freshteam.com", "zohorecruit.com", "cutshort.io",
            "darwinbox.com", "keka.com", "hirist.com",
        ],
    },

    # ──────────────────────────────────────────
    # --- Limits ---
    # ──────────────────────────────────────────
    "max_jobs_per_day": 100,
    "min_per_keyword": 10,
    "max_outreach_per_run": 20,
    "delay_between_applies_sec": (3, 8),

    # ──────────────────────────────────────────
    # --- Continuous Mode ---
    # ──────────────────────────────────────────
    "continuous_mode": True,
    "cycle_delay_minutes": 30,

    # ──────────────────────────────────────────
    # --- Behaviour ---
    # ──────────────────────────────────────────
    "headless": False,
    "dry_run": False,
}

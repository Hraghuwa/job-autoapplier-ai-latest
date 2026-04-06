# ============================================================
#  ✏️  COPY THIS FILE TO config.py AND FILL IN YOUR DETAILS
#  cp config.example.py config.py
# ============================================================

CONFIG = {
    # ──────────────────────────────────────────
    #  GEMINI AI API KEY (for personalized outreach)
    # ──────────────────────────────────────────
    "gemini_api_key": "YOUR_GEMINI_API_KEY",

    # ──────────────────────────────────────────
    #  YOUR DETAILS (pre-filled from your resume)
    # ──────────────────────────────────────────
    "name": "Your Full Name",
    "phone": "YOUR_PHONE_NUMBER",
    "email": "your.email@example.com",

    # --- Your Resume (UPDATE THIS PATH!) ---
    # Windows example: "C:/Users/YourName/Downloads/Your_Resume.pdf"
    # Mac example:     "/Users/yourname/Downloads/Your_Resume.pdf"
    "resume_path": "/path/to/your/resume.pdf",

    # --- LinkedIn Credentials ---
    "linkedin": {
        "email": "your.linkedin.email@example.com",
        "password": "YOUR_LINKEDIN_PASSWORD",
    },

    # --- Internshala Credentials ---
    "internshala": {
        "email": "your.internshala.email@example.com",
        "password": "YOUR_INTERNSHALA_PASSWORD",
    },

    # --- Unstop Credentials ---
    "unstop": {
        "email": "your.unstop.email@example.com",
        "password": "YOUR_UNSTOP_PASSWORD",
    },

    # --- Naukri Credentials ---
    "naukri": {
        "email": "your.naukri.email@example.com",
        "password": "YOUR_NAUKRI_PASSWORD",
    },

    # --- Wellfound Credentials ---
    "wellfound": {
        "email": "your.wellfound.email@example.com",
        "password": "YOUR_WELLFOUND_PASSWORD",
    },

    # ──────────────────────────────────────────
    # --- Job Preferences ---
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
        "Growth Intern"
    ],

    "locations": [
        "India",
        "Remote",
    ],

    "recently_posted": True,

    # ──────────────────────────────────────────
    # --- Role Agents ---
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

    # --- Cover Letter ---
    "cover_letter": """
I am [Your Name], currently pursuing [Your Degree] at [Your College] (2025-2027).
I am very excited to apply for this internship opportunity.

[Write your cover letter here...]

Warm regards,
[Your Name]
[Your Degree] | [Your College]
[Phone] | [Email]
""".strip(),

    # --- Profile for smart form filling ---
    "profile": {
        "full_name": "Your Full Name",
        "first_name": "First",
        "last_name": "Last",
        "gender": "Male",
        "age": "24",
        "phone": "YOUR_PHONE",
        "email": "your.email@example.com",
        "alt_email": "your.alt.email@example.com",
        "city": "Your City",
        "location": "Your City",
        "country": "India",
        "linkedin": "https://www.linkedin.com/in/your-profile/",
        "personal_website": "",

        # Education
        "degree": "MBA",
        "course": "MBA",
        "branch": "Technology Management",
        "university": "Your University",
        "college": "Your College",
        "graduation_year": "2027",

        "tenth_marks": "85",
        "twelfth_marks": "78",
        "grad_cgpa": "7.80",
        "mba_cgpa": "6.97",
        "cgpa": "7.80",
        "percentage": "78",

        "previous_degree": "Your Previous Degree",
        "previous_university": "Your Previous University",
        "previous_cgpa": "7.80",

        # Experience
        "years_experience": "4",
        "current_company": "Your Company",
        "current_role": "Your Role",
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
        "tools_used": "Gemini, Claude, Python, SQL",
        "rag_explanation": "Sourcing information directly from the origin eliminates hallucinations.",

        "google_form_name": "Your Full Name",
        "google_form_mobile": "YOUR_PHONE",
        "google_form_email": "your.email@example.com",
        "google_form_college": "Your College",
        "google_form_passing_year": "2027",

        "skills": "Product Management, Business Analysis, Python, SQL, Power BI, Figma",
        "tools": "Gemini, Claude, Figma, Python, SQL, Power BI",

        "certifications": "Your Certifications Here",

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
        "target_companies": [
            "google", "microsoft", "amazon", "meta", "flipkart",
            "razorpay", "swiggy", "zomato", "freshworks", "zoho",
        ],
        "ats_domains": [
            "lever.co", "greenhouse.io", "workday.com",
            "smartrecruiters.com", "ashbyhq.com", "cutshort.io",
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

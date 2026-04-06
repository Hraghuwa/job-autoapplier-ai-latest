# ============================================================
#  ✏️  FILL IN YOUR DETAILS HERE BEFORE RUNNING
# ============================================================

CONFIG = {
    # ──────────────────────────────────────────
    #  GEMINI AI API KEY (for personalized outreach)
    # ──────────────────────────────────────────
    "gemini_api_key": "YOUR_GEMINI_API_KEY",

    # ──────────────────────────────────────────
    #  YOUR DETAILS (pre-filled from your resume)
    # ──────────────────────────────────────────
    "name": "Harsh Raghuwanshi",
    "phone": "8109580642",
    "email": "harsh2.tapmiblr2025@learner.manipal.edu",

    # --- Your Resume (UPDATE THIS PATH!) ---
    # Windows example: "C:/Users/Harsh/Downloads/Harsh_Resume.pdf"
    # Mac example:     "/Users/harsh/Downloads/Harsh_Resume.pdf"
    "resume_path": "/Users/hragh/Desktop/251620140016_HarshRaghuwanshi_TAPMIBLR-2.pdf",

    # --- LinkedIn Credentials ---
    "linkedin": {
        "email": "hraghuwanshi3110@gmail.com",
        "password": "YOUR_LINKEDIN_PASSWORD",     # <-- Fill this!
    },

    # --- Internshala Credentials ---
    "internshala": {
        "email": "hraghuwanshi59@gmail.com",
        "password": "YOUR_INTERNSHALA_PASSWORD",  # <-- Fill this!
    },

    # --- Unstop Credentials ---
    "unstop": {
        "email": "harsh2.tapmiblr2025@learner.manipal.edu",
        "password": "YOUR_UNSTOP_PASSWORD",       # <-- Fill this!
    },

    # --- Naukri Credentials ---
    "naukri": {
        "email": "hraghuwanshi59@gmail.com",
        "password": "YOUR_NAUKRI_PASSWORD",       # <-- Fill this!
    },

    # --- Wellfound Credentials ---
    "wellfound": {
        "email": "hraghu3110@outlook.com",
        "password": "YOUR_WELLFOUND_PASSWORD",
    },

    # ──────────────────────────────────────────
    # --- Job Preferences ---
    # ──────────────────────────────────────────
    "keywords": [
        "Product Management Intern",
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

    # Filter for recently posted jobs (used by platforms that support it)
    "recently_posted": True,

    # ──────────────────────────────────────────
    # --- Role Agents (each agent runs across ALL platforms sequentially) ---
    # ──────────────────────────────────────────
    "role_agents": [
        {
            "name": "AI & Management",
            "emoji": "🧠",
            "keywords": [
                "AI Management Intern",
                "AI Intern",
                "AI Product Manager Intern",
                "AI Strategy Intern",
                "Generative AI Intern",
                "AI Business Analyst",
                "Machine Learning Intern",
                "AI Operations Intern",
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
                "Program Manager Intern",
                "Project Manager Intern",
            ],
        },
    ],

    # --- Cover Letter (auto-filled from your background) ---
    "cover_letter": """
I am Harsh Raghuwanshi, currently pursuing MBA TECH at TAPMI Bengaluru (2025-2027).
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
8109580642 | harsh2.tapmiblr2025@learner.manipal.edu
""".strip(),

    # --- Profile for smart form filling ---
    "profile": {
        "full_name": "Harsh Raghuwanshi",
        "first_name": "Harsh",
        "last_name": "Raghuwanshi",
        "gender": "Male",
        "age": "24",
        "phone": "8109580642",
        "email": "hraghu3110@outlook.com",
        "alt_email": "harsh2.tapmiblr2025@learner.manipal.edu",
        "city": "Bangalore",
        "location": "Bangalore",
        "country": "India",
        "linkedin": "https://www.linkedin.com/in/harsh-raghuwanshi-570868359/",

        # Education
        "degree": "MBA",
        "course": "MBA",
        "branch": "Technology Management",
        "university": "Manipal/T.A Pai Management Institute",
        "college": "Manipal/T.A Pai Management Institute",
        "graduation_year": "2027",

        # Education marks (separate for each level)
        "tenth_marks": "85",       # 10th percentage
        "twelfth_marks": "78",     # 12th percentage
        "grad_cgpa": "7.80",       # Graduation CGPA (BA Programme, Delhi University)
        "mba_cgpa": "6.97",        # MBA CGPA (TAPMI)
        "cgpa": "7.80",            # Default CGPA (graduation)
        "percentage": "78",        # Default percentage (12th)

        "previous_degree": "BA Programme (Political Science & Computer Applications)",
        "previous_university": "University of Delhi",
        "previous_cgpa": "7.80",

        # Experience
        "years_experience": "4",
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

        # AI / Product experience
        "has_product_ai_experience": "Yes",
        "tools_used": "Google AI Studio, Anti Gravity, Replit, Gemini, Claude",
        "rag_explanation": "Sourcing information directly from the origin eliminates hallucinations.",

        # Google Form specific
        "google_form_name": "Harsh Raghuwanshi",
        "google_form_mobile": "8109580642",
        "google_form_email": "hraghu3110@outlook.com",
        "google_form_college": "Manipal/T.A Pai Management Institute",
        "google_form_passing_year": "2027",

        # Skills
        "skills": "Product Management, Product Roadmapping, Requirements Gathering, Story Mapping, Design Thinking, Market Research, Data Analysis, Python, SQL, Power BI, Figma, ERP, CRM, AI Tools (Gemini, Claude), n8n, Shopify, GTM Strategy",
        "tools": "Google AI Studio, Anti Gravity, Replit, Gemini, Claude, Figma, Python, SQL, Power BI, n8n",

        # Certifications
        "certifications": "IBM AI Product Manager, Stanford IoT Fundamentals, AWS Cloud Practitioner (Pursuing), Finlatics Generative AI Programme",

        # Quick answers for common form fields
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
            "postman", "browserstack", "hasura", "razorpay",
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
    "min_per_keyword": 10,  # Apply to at least 10 jobs per keyword
    "delay_between_applies_sec": (3, 8),   # random delay range in seconds

    # ──────────────────────────────────────────
    # --- Continuous Mode ---
    # ──────────────────────────────────────────
    "continuous_mode": True,         # 🔁 Keep looping forever
    "cycle_delay_minutes": 30,       # ⏱️  Wait between cycles (minutes)

    # ──────────────────────────────────────────
    # --- Behaviour ---
    # ──────────────────────────────────────────
    "headless": False,    # Set True to run browser in background
    "dry_run": False,      # ⚠️ SET TO False WHEN READY TO ACTUALLY APPLY!
}

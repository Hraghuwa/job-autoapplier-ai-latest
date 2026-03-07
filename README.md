# 🤖 Job Auto-Applier — Setup Guide

Automatically applies to Tech Consulting & Business Development internships
across LinkedIn, Internshala, Unstop, and Naukri in India.

---

## ⚙️ SETUP (One Time)

### Step 1 — Install Python
Download from https://python.org (version 3.9+)

### Step 2 — Install Google Chrome
Download from https://google.com/chrome

### Step 3 — Install dependencies
Open terminal in this folder and run:
```
pip install -r requirements.txt
```

### Step 4 — Fill in your details
Open `config.py` and update:

| Field | What to enter |
|-------|--------------|
| `resume_path` | Full path to your resume PDF e.g. `C:/Users/YourName/resume.pdf` |
| `linkedin > email` | Your LinkedIn email |
| `linkedin > password` | Your LinkedIn password |
| `internshala > email` | Your Internshala email |
| `internshala > password` | Your Internshala password |
| `unstop > email` | Your Unstop email |
| `unstop > password` | Your Unstop password |
| `naukri > email` | Your Naukri email |
| `naukri > password` | Your Naukri password |

---

## ▶️ HOW TO RUN

```bash
python main.py
```

The browser will open and start applying automatically!

---

## 🧪 TEST FIRST (Dry Run)

In `config.py`, set:
```python
"dry_run": True
```
This will go through all the motions WITHOUT actually clicking Apply.
Change back to `False` when ready for real applications.

---

## 📊 TRACKING

- Applied jobs are tracked in `applied_jobs.json`
- Check it anytime to see your total count

---

## ⚠️ IMPORTANT TIPS

1. **Don't run 24/7** — max 15 applications/day to stay safe
2. **Watch for CAPTCHAs** — solve them manually if they appear (run with `headless: False`)
3. **LinkedIn may ask for verification** — have your phone ready
4. **Keep the browser window visible** while running
5. **Run once per day** — not multiple times

---

## 🆘 TROUBLESHOOTING

| Problem | Fix |
|---------|-----|
| `chromedriver` error | Run `pip install --upgrade webdriver-manager` |
| Login fails | Check credentials in config.py |
| CAPTCHA appears | Solve it manually, script will continue |
| "Resume not found" | Check the resume_path in config.py |

---

Happy job hunting! 🚀

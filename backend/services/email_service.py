"""Email notifications via Resend SDK."""
from typing import Optional, List
from backend.config import settings


def send_email(to: str, subject: str, html: str) -> bool:
    if not settings.resend_api_key:
        return False  # Email not configured — skip silently
    try:
        import resend
        resend.api_key = settings.resend_api_key
        resend.Emails.send({
            "from": "JobAgent <noreply@jobagent.app>",
            "to": [to],
            "subject": subject,
            "html": html,
        })
        return True
    except Exception:
        return False


def send_welcome(email: str, name: str) -> bool:
    return send_email(
        email,
        "Welcome to JobAgent!",
        f"""<h2>Hi {name},</h2>
<p>Your account is ready. Start by completing your onboarding:</p>
<ol>
<li>Upload your resume</li>
<li>Set job preferences</li>
<li>Add platform credentials</li>
<li>Review your autofill bank</li>
</ol>
<a href="{settings.frontend_url}/onboarding">Start Onboarding →</a>""",
    )


def send_run_complete(email: str, name: str, applied: int, skipped: int, platform: str) -> bool:
    return send_email(
        email,
        f"JobAgent: Applied to {applied} jobs on {platform}",
        f"""<h2>Run Complete!</h2>
<p>Hi {name}, here's your summary:</p>
<ul>
<li>✅ Applied: {applied}</li>
<li>⏭️ Skipped: {skipped}</li>
<li>🌐 Platform: {platform}</li>
</ul>
<a href="{settings.frontend_url}/jobs">View Applications →</a>""",
    )


def send_status_change(email: str, name: str, company: str, job_title: str, new_status: str) -> bool:
    return send_email(
        email,
        f"Update: {company} — {new_status}",
        f"""<h2>Application Update</h2>
<p>Hi {name}, your application status changed:</p>
<p><strong>{job_title}</strong> at <strong>{company}</strong><br>
Status: <strong>{new_status.upper()}</strong></p>
<a href="{settings.frontend_url}/jobs">View in JobAgent →</a>""",
    )


def send_payment_receipt(email: str, name: str, amount_inr: float, plan: str) -> bool:
    return send_email(
        email,
        f"Receipt: JobAgent {plan.title()} Plan",
        f"""<h2>Payment Confirmed</h2>
<p>Hi {name}, thank you for upgrading!</p>
<p>Amount: ₹{amount_inr:.0f}<br>Plan: {plan.title()}</p>
<a href="{settings.frontend_url}/settings/billing">View Billing →</a>""",
    )

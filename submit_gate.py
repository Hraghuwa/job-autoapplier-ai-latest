"""
🛑 Submit Safety Gate — Human-in-the-Loop Guard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NON-NEGOTIABLE: The agent must NEVER submit an application by itself.

This module provides a single choke-point that EVERY applier must call
before clicking any submit/apply button.  If config["auto_submit"] is
False (the default), the gate BLOCKS the click and prints a clear
"⏸ PAUSED" message so the human can review and submit manually.

Usage in every applier:
    from submit_gate import safety_gate
    if not safety_gate(config, label="LinkedIn Easy Apply"):
        return "review"   # stop — do NOT click submit
    # ... click submit ...
"""


def safety_gate(config, label=""):
    """Return True only when automated submission is explicitly allowed.

    Parameters
    ----------
    config : dict
        The global CONFIG dict.  Must contain ``auto_submit`` (bool).
        Missing key → treated as False (safe default).
    label : str
        Human-readable context printed in the pause message, e.g.
        "LinkedIn Easy Apply" or "Wellfound modal".

    Returns
    -------
    bool
        True  → caller may proceed to click submit.
        False → caller must STOP and leave the form open for human review.
    """
    auto_submit = bool(config.get("auto_submit", False))

    if auto_submit:
        return True

    # ── BLOCK: human must review ──
    tag = f" [{label}]" if label else ""
    print(f"  ⏸  PAUSED{tag} — form filled, ready for YOUR review.")
    print(f"  👉 Review the form in the browser and click Submit manually.")
    print(f"  💡 To let the agent submit automatically, set auto_submit=True in config.")
    return False
"""Module: submit_gate — central human-in-the-loop guard for application submission."""

// content.js - Injected by the extension popup

async function fillFormFields() {
    console.log("[Smart Fill] Starting to fill form fields...");

    // Ensure CONFIG_DATA is loaded (from data.js)
    if (typeof CONFIG_DATA === 'undefined') {
        console.error("[Smart Fill] CONFIG_DATA is missing. Did build_extension.py run?");
        return;
    }

    const profile = CONFIG_DATA.profile || {};
    const name = profile.name || CONFIG_DATA.name || "";
    const email = profile.email || CONFIG_DATA.email || "";
    const phone = profile.phone || CONFIG_DATA.phone || "";
    const linkedin = profile.linkedin || "";
    const github = profile.github || "";
    const portfolio = profile.portfolio || "";
    const location = profile.location || "";

    let filledCount = 0;

    // --- Helper to set value and trigger events ---
    function setInputValue(input, value) {
        if (!input || !value) return false;
        if (input.value === value) return false; // Already set

        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        input.dispatchEvent(new Event('blur', { bubbles: true }));

        // Handle React/Vue specific hidden setters if needed
        let tracker = input._valueTracker;
        if (tracker) tracker.setValue(value);

        return true;
    }

    // --- 1. Fill Text Inputs ---
    const textInputs = document.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input[type="url"], input:not([type]), textarea');

    textInputs.forEach(input => {
        // Skip hidden or disabled inputs
        if (input.type === 'hidden' || input.disabled || input.readOnly || input.offsetParent === null) return;

        const type = (input.type || "").toLowerCase();
        const nameAttr = (input.name || "").toLowerCase();
        const idAttr = (input.id || "").toLowerCase();
        const labelSafe = (input.getAttribute('aria-label') || input.placeholder || "").toLowerCase();
        const fullText = `${type} ${nameAttr} ${idAttr} ${labelSafe}`;

        let valueToFill = null;

        if (fullText.includes("first") && fullText.includes("name")) {
            valueToFill = name.split(" ")[0] || name;
        } else if (fullText.includes("last") && fullText.includes("name")) {
            valueToFill = name.split(" ").slice(1).join(" ") || "Applicant";
        } else if (fullText.includes("name") || fullText.includes("full")) {
            valueToFill = name;
        } else if (fullText.includes("email") || type === 'email') {
            valueToFill = email;
        } else if (fullText.includes("phone") || fullText.includes("mobile") || type === 'tel') {
            valueToFill = phone;
        } else if (fullText.includes("linkedin") || fullText.includes("linked id")) {
            valueToFill = linkedin;
        } else if (fullText.includes("github")) {
            valueToFill = github;
        } else if (fullText.includes("portfolio") || fullText.includes("website")) {
            valueToFill = portfolio;
        } else if (fullText.includes("location") || fullText.includes("city")) {
            valueToFill = location;
        } else if (fullText.includes("experience") && type === 'number') {
            valueToFill = "1"; // Default to 1 yr for intern
        }

        if (valueToFill && setInputValue(input, valueToFill)) {
            input.style.backgroundColor = "#e8f0fe"; // Highlight filled fields
            filledCount++;
            console.log(`[Smart Fill] Filled ${nameAttr || idAttr} with ${valueToFill}`);
        }
    });

    // --- 2. Radio Buttons & Checkboxes (Heuristics) ---
    // Auto-select "Yes" for authorization, sponsorship, or 18+ questions
    const radiosAndChecks = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');

    radiosAndChecks.forEach(input => {
        if (input.checked || input.disabled || input.offsetParent === null) return;

        // Find associated label text
        let labelText = "";
        if (input.id) {
            const label = document.querySelector(`label[for="${input.id}"]`);
            if (label) labelText = label.innerText.toLowerCase();
        }
        if (!labelText) {
            const parent = input.closest('label');
            if (parent) labelText = parent.innerText.toLowerCase();
        }
        if (!labelText) {
            labelText = (input.value || "").toLowerCase();
        }

        const value = (input.value || "").toLowerCase();
        const inputName = (input.name || "").toLowerCase();

        // Questions where we want to say "Yes"
        const yesTerms = ["yes", "true", "agree", "i agree", "accept"];
        const authorizationQs = ["authorized", "sponsorship", "require visa", "relocate", "commute"];

        if (yesTerms.includes(labelText) || yesTerms.includes(value)) {
            // Only click if it's a positive response to a standard question
            input.click();
            filledCount++;
            console.log(`[Smart Fill] Checked ${inputName} (${labelText})`);
        }
    });

    return filledCount;
}

// Execute immediately when injected
fillFormFields().then(count => {
    console.log(`[Smart Fill] Completed. Filled ${count} fields.`);
});

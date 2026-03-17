document.getElementById('fillBtn').addEventListener('click', async () => {
    const status = document.getElementById('status');
    status.innerHTML = "Scanning fields...";
    
    // Get the active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    
    // Execute content.js and inject data.js first
    try {
        await chrome.scripting.executeScript({
            target: { tabId: tab.id },
            files: ['data.js', 'content.js']
        });
        
        status.innerHTML = "<span class='check'>✓</span> Form filled!";
        setTimeout(() => window.close(), 1500);
    } catch (e) {
        status.innerHTML = `Error: ${e.message}`;
    }
});

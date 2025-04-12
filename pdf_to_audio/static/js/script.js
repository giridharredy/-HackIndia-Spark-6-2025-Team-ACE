document.addEventListener('DOMContentLoaded', () => {
    // --- Get DOM Elements ---
    const form = document.getElementById('upload-form');
    const statusDiv = document.getElementById('status');
    const playerSection = document.getElementById('player-section');
    const playerPlaceholder = document.getElementById('player-placeholder');
    const player = document.getElementById('player');

    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('pdf_file'); // The actual hidden input
    const fileNameDisplay = document.getElementById('file-name-display');

    // Controls (hidden, but needed for form data)
    const voiceSelect = document.getElementById('voice');
    // Stability elements ADDED BACK
    const stabilitySlider = document.getElementById('stability');
    const stabilityValueSpan = document.getElementById('stability-value'); // For hidden input display logic if needed

    // --- Function to Update Slider Value Display (If needed for hidden span) ---
    // This might not be strictly necessary if the span isn't visible,
    // but good practice to keep it if the hidden span exists.
    function updateSliderValue(slider, span) {
        if (slider && span) {
            span.textContent = parseFloat(slider.value).toFixed(2); // Initial display
            slider.addEventListener('input', () => { // Use 'input' for live updates
                span.textContent = parseFloat(slider.value).toFixed(2);
            });
        }
    }
    // Call it again for stability
    updateSliderValue(stabilitySlider, stabilityValueSpan);


    // --- Function to Update Status Area ---
    function updateStatus(message, type = 'info') {
        // ... (Keep existing logic) ...
        if (!statusDiv) return;
        statusDiv.textContent = message;
        statusDiv.className = 'alert';
        statusDiv.classList.add(`alert-${type}`);
        statusDiv.classList.remove('hidden');
    }

    // --- Function to Show/Hide Player vs Placeholder ---
    function showPlayer(show = true) {
        // ... (Keep existing logic) ...
         if (!playerSection) return;
        if (show) {
            playerSection.classList.add('active');
            player.classList.remove('hidden');
            playerPlaceholder?.classList.add('hidden');
        } else {
            playerSection.classList.remove('active');
            player.classList.add('hidden');
            player.src = '';
            playerPlaceholder?.classList.remove('hidden');
        }
    }

    // --- Function to Reset UI ---
    function resetUI() {
        // ... (Keep existing logic) ...
        if (statusDiv) statusDiv.classList.add('hidden');
        showPlayer(false);
        if (fileNameDisplay) fileNameDisplay.textContent = '';
        if (fileInput) fileInput.value = '';
        if (uploadArea) uploadArea.classList.remove('dragover');
    }

    // --- Handle File Display & Assignment ---
    function handleFileSelect(file) {
        // ... (Keep existing logic) ...
        resetUI();
        if (file && (file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.epub'))) {
            const dataTransfer = new DataTransfer();
            dataTransfer.items.add(file);
            fileInput.files = dataTransfer.files;
            if (fileNameDisplay) { fileNameDisplay.textContent = `File ready: ${file.name}`; }
            if (statusDiv) statusDiv.classList.add('hidden');
            triggerProcessing(); // Auto-trigger
        } else {
            updateStatus('Invalid file type. Please upload a PDF or EPUB.', 'danger');
            if (fileNameDisplay) fileNameDisplay.textContent = 'Invalid file type.';
        }
    }

    // --- Drag and Drop Event Listeners ---
    if (uploadArea && fileInput) {
       // ... (Keep existing drag/drop logic) ...
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); }, false);
        });
        ['dragenter', 'dragover'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => { uploadArea.classList.add('dragover'); }, false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
            uploadArea.addEventListener(eventName, () => { uploadArea.classList.remove('dragover'); }, false);
        });
        uploadArea.addEventListener('drop', (e) => {
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) { handleFileSelect(e.dataTransfer.files[0]); }
        }, false);
        fileInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files.length > 0) { handleFileSelect(e.target.files[0]); }
        });
    } else {
        console.error("Upload area or file input element not found.");
    }


    // --- Function to Trigger Processing ---
    async function triggerProcessing() {
        // --- Validation (Add stability check if needed, browser handles range mostly) ---
        if (!fileInput || !fileInput.files || fileInput.files.length === 0) { /*...*/ return; }
        if (!voiceSelect || !voiceSelect.value) { /*...*/ return; }
        // Optional: Check if stability slider exists and has a valid value if you want stricter JS validation
        // if (!stabilitySlider || stabilitySlider.value === '') { ... }

        // --- Update UI: Show Processing ---
        showPlayer(false);
        updateStatus('Processing... Please wait.', 'info');
        if (uploadArea) uploadArea.style.pointerEvents = 'none';

        // --- Prepare and Send Data ---
        const formData = new FormData(form); // Will now include stability again

        try {
            const response = await fetch('/process', {
                method: 'POST',
                body: formData
            });

            // --- Handle Response ---
            let result;
            try {
                 result = await response.json();
            } catch (e) { /*...*/ return; }
            finally { if (uploadArea) uploadArea.style.pointerEvents = 'auto'; }

            if (response.ok && result.status === 'success') {
                // ... (Keep existing success logic) ...
                updateStatus(result.message || 'Audio generated successfully!', 'success');
                if (result.audio_url && player) { player.src = result.audio_url; showPlayer(true); }
                else { updateStatus('Processing succeeded, but could not find the audio file URL.', 'warning'); showPlayer(false); }
            } else {
                // ... (Keep existing error logic) ...
                 console.error("Backend Error:", result);
                 updateStatus(`Error: ${result.message || `An unknown error occurred (Status: ${response.status})`}`, 'danger');
                 showPlayer(false);
            }

        } catch (error) {
             // ... (Keep existing network error logic) ...
             console.error('Network/Fetch Error:', error);
             updateStatus(`Network error: Could not connect. (${error.message || 'Unknown fetch error'})`, 'danger');
             showPlayer(false);
             if (uploadArea) uploadArea.style.pointerEvents = 'auto';
        }
    } // End of triggerProcessing

    // --- Initialize UI ---
    resetUI(); // Start with a clean state

}); // End DOMContentLoaded
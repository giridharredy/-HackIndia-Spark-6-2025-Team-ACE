document.addEventListener('DOMContentLoaded', () => {
    // --- Get DOM Elements ---
    const form = document.getElementById('upload-form');
    const submitButton = document.getElementById('submit-button');
    const statusDiv = document.getElementById('status');
    const playerContainer = document.getElementById('player-container');
    const player = document.getElementById('player');
    const pdfInput = document.getElementById('pdf_file');
    const voiceSelect = document.getElementById('voice');

    // --- Sliders and Value Displays ---
    const stabilitySlider = document.getElementById('stability');
    const stabilityValueSpan = document.getElementById('stability-value');
    const similaritySlider = document.getElementById('similarity');
    const similarityValueSpan = document.getElementById('similarity-value');

    // --- NEW: Book Progress Elements ---
    const bookProgressSidebar = document.getElementById('book-progress-sidebar');
    const progressBarFill = document.getElementById('progress-bar-fill');
    const progressPercentage = document.getElementById('progress-percentage');

    // --- Function to Update Slider Value Display ---
    function updateSliderValue(slider, span) {
        if (slider && span) {
            span.textContent = parseFloat(slider.value).toFixed(2);
            slider.addEventListener('input', () => {
                span.textContent = parseFloat(slider.value).toFixed(2);
            });
        }
    }

    updateSliderValue(stabilitySlider, stabilityValueSpan);
    updateSliderValue(similaritySlider, similarityValueSpan);

    // --- Function to Update Status Area ---
    function updateStatus(message, type = 'info') {
        if (!statusDiv) return;
        statusDiv.textContent = message;
        statusDiv.className = 'alert';
        statusDiv.classList.add(`alert-${type}`);
        statusDiv.classList.remove('hidden');
    }

    // --- Function to Hide Status and Player ---
    function resetUI() {
        if (statusDiv) statusDiv.classList.add('hidden');
        if (playerContainer) playerContainer.classList.add('hidden');
        if (player) player.src = '';
        if (submitButton) {
             submitButton.disabled = false;
             // Reset icon along with text
             submitButton.innerHTML = '<i class="fas fa-play"></i> Generate Audio';
        }
        // NEW: Hide progress bar on UI reset
        if (bookProgressSidebar) bookProgressSidebar.classList.add('hidden');
        if (progressBarFill) progressBarFill.style.height = '0%';
        if (progressPercentage) progressPercentage.textContent = '0%';
    }

    // --- Clear Status/Player on New File Selection ---
    if (pdfInput) {
        pdfInput.addEventListener('change', () => {
            if (statusDiv) statusDiv.classList.add('hidden');
            if (playerContainer) playerContainer.classList.add('hidden');
            if (player) player.src = '';
            // NEW: Hide progress bar when file changes
             if (bookProgressSidebar) bookProgressSidebar.classList.add('hidden');
             if (progressBarFill) progressBarFill.style.height = '0%';
             if (progressPercentage) progressPercentage.textContent = '0%';
        });
    }

    // --- Handle Form Submission ---
    if (form) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();

            if (!pdfInput.files || pdfInput.files.length === 0) {
                updateStatus('Please select a PDF file.', 'danger');
                return;
            }
            const file = pdfInput.files[0];
            if (file.type !== 'application/pdf') {
                 updateStatus('Selected file is not a PDF. Please upload a valid PDF file.', 'danger');
                 return;
            }
            if (!voiceSelect || !voiceSelect.value) {
                 updateStatus('Please select a voice.', 'danger');
                 return;
            }

            resetUI();
            updateStatus('Processing... Please wait.', 'info');
            submitButton.disabled = true;
             // Update icon during processing
            submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

            const formData = new FormData(form);

            try {
                const response = await fetch('/process', {
                    method: 'POST',
                    body: formData
                });

                let result;
                try {
                     result = await response.json();
                } catch (e) {
                     console.error("Failed to parse response as JSON:", e);
                     const errorText = await response.text();
                     updateStatus(`Server error (Status ${response.status}): ${errorText.substring(0, 200)}...`, 'danger');
                     submitButton.disabled = false;
                     submitButton.innerHTML = '<i class="fas fa-play"></i> Generate Audio';
                     return;
                }

                if (response.ok && result.status === 'success') {
                    updateStatus(result.message || 'Audio generated successfully!', 'success');
                    if (result.audio_url && player && playerContainer && bookProgressSidebar) { // Check sidebar too
                        player.src = result.audio_url;
                        playerContainer.classList.remove('hidden');
                        // NEW: Show the progress sidebar when audio is ready
                        bookProgressSidebar.classList.remove('hidden');
                    } else {
                         console.warn("Success response received, but no audio URL or required elements found:", result);
                         updateStatus('Processing succeeded, but could not find the audio file URL or UI elements.', 'warning');
                    }
                    submitButton.disabled = false;
                    submitButton.innerHTML = '<i class="fas fa-play"></i> Generate Audio';

                } else {
                    console.error("Backend Error:", result);
                    updateStatus(`Error: ${result.message || `An unknown error occurred (Status: ${response.status})`}`, 'danger');
                     submitButton.disabled = false;
                     submitButton.innerHTML = '<i class="fas fa-play"></i> Generate Audio';
                }

            } catch (error) {
                console.error('Network/Fetch Error:', error);
                updateStatus(`Network error: Could not connect to the server. (${error.message || 'Unknown fetch error'})`, 'danger');
                 submitButton.disabled = false;
                 submitButton.innerHTML = '<i class="fas fa-play"></i> Generate Audio';
            }
        });
    } else {
        console.error("Could not find the upload form element (#upload-form).");
    }

    // --- NEW: Audio Playback Progress Update ---
    if (player && progressBarFill && progressPercentage) {
        player.addEventListener('timeupdate', () => {
            if (player.duration && !isNaN(player.duration)) {
                const progress = (player.currentTime / player.duration) * 100;
                progressBarFill.style.height = `${progress}%`;
                progressPercentage.textContent = `${Math.round(progress)}%`;
            } else {
                 // Handle cases where duration isn't available yet (e.g., initial load)
                 progressBarFill.style.height = '0%';
                 progressPercentage.textContent = '0%';
            }
        });

        // Reset progress when audio ends or is paused/stopped manually
         player.addEventListener('ended', () => {
             // Optional: Keep progress at 100% on end, or reset
             // progressBarFill.style.height = '0%';
             // progressPercentage.textContent = '0%';
         });
          player.addEventListener('pause', () => {
              // Update state if needed when paused
          });
           // Reset when src changes (e.g., new file loaded)
           player.addEventListener('emptied', () => {
             progressBarFill.style.height = '0%';
             progressPercentage.textContent = '0%';
          });

    } else {
        console.error("Could not find player or progress bar elements for audio progress updates.");
    }


}); // End DOMContentLoaded
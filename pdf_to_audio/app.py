import os
import fitz  # PyMuPDF
from flask import Flask, request, jsonify, render_template, send_from_directory
from elevenlabs.client import ElevenLabs
from elevenlabs import Voice, VoiceSettings, save
import httpx
from dotenv import load_dotenv
import time
import traceback
import secrets # For generating secure random filenames
import logging # For better logging
from datetime import datetime # For potential future use

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration & Initialization ---
load_dotenv()
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")

# --- Flask App Setup ---
app = Flask(__name__)
# Configure directories
AUDIO_FOLDER = os.path.join('static', 'audio')
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['AUDIO_FOLDER'] = AUDIO_FOLDER
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Ensure directories exist
os.makedirs(app.config['AUDIO_FOLDER'], exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- ElevenLabs Client Setup ---
client = None
ELEVENLABS_VOICES_CACHE = None
VOICE_FETCH_ERROR = None

logging.info("Initializing ElevenLabs Client...")
if elevenlabs_api_key:
    try:
        client = ElevenLabs(api_key=elevenlabs_api_key)
        # Attempt to fetch voices on startup to populate cache
        try:
            ELEVENLABS_VOICES_CACHE = client.voices.get_all()
            if ELEVENLABS_VOICES_CACHE and ELEVENLABS_VOICES_CACHE.voices:
                 logging.info(f"Successfully fetched {len(ELEVENLABS_VOICES_CACHE.voices)} voices during startup.")
            else:
                 logging.warning("Fetched voices during startup but the list is empty or invalid.")
                 VOICE_FETCH_ERROR = "Voice list received from API was empty or invalid during startup."
        except Exception as e_fetch:
             logging.error(f"Failed to fetch voices during startup: {e_fetch}", exc_info=True)
             VOICE_FETCH_ERROR = f"Failed to fetch voices during startup: {e_fetch}"
             # Keep client initialized, will try again later if needed

        logging.info("ElevenLabs client initialized.")
    except httpx.HTTPStatusError as e:
        VOICE_FETCH_ERROR = f"API HTTP Error during client initialization: {e.response.status_code} - {e.response.text}"
        logging.error(VOICE_FETCH_ERROR, exc_info=True)
        client = None # Client init failed
    except Exception as e:
        VOICE_FETCH_ERROR = f"Unexpected error during client initialization: {type(e).__name__} - {e}"
        logging.error(VOICE_FETCH_ERROR, exc_info=True)
        client = None # Client init failed
else:
    VOICE_FETCH_ERROR = "ERROR: ELEVENLABS_API_KEY not found in .env file."
    logging.error(VOICE_FETCH_ERROR)

# --- Helper Functions ---

def extract_text_from_pdf(pdf_file_path):
    """Extracts text from a single PDF file."""
    # NOTE: Add EPUB handling here if needed using another library like EbookLib
    if not pdf_file_path.lower().endswith('.pdf'):
         logging.warning(f"Attempted text extraction from non-PDF file: {pdf_file_path}")
         # For now, raise an error. Adapt if EPUB is fully supported.
         raise ValueError("Currently only PDF text extraction is supported.")

    try:
        doc = fitz.open(pdf_file_path)
        full_text = ""
        total_pages = len(doc)
        logging.info(f"Extracting text from '{os.path.basename(pdf_file_path)}' ({total_pages} pages)...")
        for page_num in range(total_pages):
            page = doc.load_page(page_num)
            full_text += page.get_text("text")
        doc.close()
        logging.info(f"Text extracted. Length: {len(full_text)} characters.")
        if not full_text.strip():
             logging.warning(f"PDF '{os.path.basename(pdf_file_path)}' contained no extractable text.")
        return full_text
    except Exception as e:
        logging.error(f"Error extracting text from PDF '{os.path.basename(pdf_file_path)}': {e}", exc_info=True)
        raise ValueError(f"Error processing PDF file: {e}")

def get_voices_with_retry():
    """Attempts to fetch voices, using cache if available, retrying if necessary."""
    global ELEVENLABS_VOICES_CACHE, VOICE_FETCH_ERROR
    if ELEVENLABS_VOICES_CACHE and ELEVENLABS_VOICES_CACHE.voices:
        logging.info("Using cached voices list.")
        return ELEVENLABS_VOICES_CACHE.voices

    if not client:
         raise ConnectionError(f"Cannot fetch voices: ElevenLabs client not initialized. Error: {VOICE_FETCH_ERROR or 'Unknown initialization error'}")

    logging.info("Attempting to fetch/re-fetch voices list from ElevenLabs API...")
    try:
        voices_response = client.voices.get_all()
        if voices_response and voices_response.voices:
            ELEVENLABS_VOICES_CACHE = voices_response # Update cache
            logging.info(f"Successfully fetched {len(ELEVENLABS_VOICES_CACHE.voices)} voices.")
            VOICE_FETCH_ERROR = None # Clear any previous fetch error
            return ELEVENLABS_VOICES_CACHE.voices
        else:
            logging.error("API returned empty or invalid voice list.")
            raise ConnectionError("Failed to fetch a valid voice list from ElevenLabs (empty list received).")
    except httpx.HTTPStatusError as e:
        logging.error(f"API Error fetching voices list: {e.response.status_code} - {e.response.text}", exc_info=True)
        VOICE_FETCH_ERROR = f"API Error fetching voices: Status {e.response.status_code}"
        raise ConnectionError(VOICE_FETCH_ERROR)
    except Exception as e:
        logging.error(f"Unexpected error fetching voices list: {e}", exc_info=True)
        VOICE_FETCH_ERROR = f"Unexpected error fetching voices: {e}"
        raise ConnectionError(VOICE_FETCH_ERROR)

def text_to_elevenlabs_audio(text_to_speak, voice_name, stability, similarity, output_filepath):
    """Converts text to speech using the ElevenLabs client and saves to a file."""
    # Similarity is currently not used in the UI, but kept in function signature
    if not client:
        raise ConnectionError(f"ElevenLabs client not available. Init Error: {VOICE_FETCH_ERROR or 'Unknown initialization error'}")
    if not text_to_speak or not text_to_speak.strip():
        raise ValueError("No text provided to convert to speech.")

    try:
         available_voices = get_voices_with_retry() # Fetch or use cache
    except ConnectionError as e:
         logging.error(f"Failed to get available voices: {e}")
         raise ConnectionError(f"Could not confirm available voices before generation: {e}")

    selected_voice_obj = next((v for v in available_voices if v.name.lower() == voice_name.lower()), None)

    if not selected_voice_obj:
        available_names = [v.name for v in available_voices]
        logging.error(f"Selected voice '{voice_name}' not found. Available: {available_names}")
        raise ValueError(f"Selected voice '{voice_name}' not found. Available voices are: {', '.join(available_names)}")

    logging.info(f"Requesting audio generation for voice '{selected_voice_obj.name}' (ID: {selected_voice_obj.voice_id}) with stability {stability}")

    MAX_CHARS = 4800 # Keep truncation conservative
    if len(text_to_speak) > MAX_CHARS:
        logging.warning(f"Text too long ({len(text_to_speak)} chars). Truncating to {MAX_CHARS}.")
        text_to_speak = text_to_speak[:MAX_CHARS]

    try:
        # Use default similarity for now as it's not in the UI
        default_similarity = 0.75
        audio_data = client.generate(
            text=text_to_speak,
            voice=Voice(
                voice_id=selected_voice_obj.voice_id,
                settings=VoiceSettings(stability=float(stability), similarity_boost=float(default_similarity))
            ),
            model='eleven_multilingual_v2'
        )

        if audio_data:
            save(audio_data, output_filepath)
            logging.info(f"Audio successfully generated and saved to {output_filepath}")
            return output_filepath
        else:
            logging.error("Audio generation returned empty data without raising an exception.")
            raise ConnectionError("Failed to generate audio data (received empty response).")

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_body = "No details available"
        try: error_body = e.response.json().get('detail', {}).get('message', e.response.text)
        except: error_body = e.response.text

        logging.error(f"API HTTP Error during audio generation: Status {status_code}, Response: {error_body}", exc_info=False)
        if status_code == 401: raise PermissionError(f"Authentication Error (Check API Key). Status: {status_code}")
        elif status_code == 400 and "text length" in error_body.lower():
             raise ValueError(f"Text too long for API request (limit might be ~5000 chars). Status: {status_code}")
        elif status_code == 400: raise ValueError(f"Bad Request (Check voice/settings/text). Status: {status_code}. Details: {error_body}")
        elif status_code == 402: raise PermissionError(f"Payment Required or Quota Exceeded. Status: {status_code}")
        elif status_code == 429: raise ConnectionError(f"Rate Limit Exceeded. Please wait before trying again. Status: {status_code}")
        else: raise ConnectionError(f"API Error during audio generation: Status Code {status_code}. Details: {error_body}")
    except Exception as e:
        logging.error(f"Unexpected error during audio generation: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected error during audio generation: {e}")

# --- Flask Routes ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    logging.info("Serving index.html for PageToPlay layout")
    voice_names = ["Rachel", "Adam", "Antoni", "Sarah", "Emily"] # Default fallback
    current_error = VOICE_FETCH_ERROR

    try:
        available_voices = get_voices_with_retry()
        voice_names = sorted([v.name for v in available_voices])
        current_error = None
    except ConnectionError as e:
        logging.warning(f"Could not get voices for index page, using defaults. Error: {e}")
        current_error = str(e)
    except Exception as e:
         logging.error(f"Unexpected error getting voices for index page: {e}", exc_info=True)
         current_error = f"Unexpected error loading voices: {e}"

    return render_template('index.html', voices=voice_names, error_message=current_error)


@app.route('/process', methods=['POST'])
def process_pdf():
    """Handles file upload, processing, and returns audio info."""
    logging.info("Received request for /process")
    start_time = time.time()
    temp_filepath = None
    original_filename = "N/A"

    if 'pdf_file' not in request.files:
        logging.warning("No file part in request")
        return jsonify({"status": "error", "message": "No file part in the request."}), 400

    file = request.files['pdf_file']
    if not file or file.filename == '':
        logging.warning("No selected file")
        return jsonify({"status": "error", "message": "No file selected or filename is empty."}), 400

    original_filename = file.filename
    # Basic check for supported extensions (adapt if EPUB handling is added)
    allowed_extensions = {'.pdf'} # Add '.epub' if supported later
    file_ext = os.path.splitext(original_filename)[1].lower()
    if file_ext not in allowed_extensions:
        logging.warning(f"Invalid file type uploaded: {original_filename}")
        return jsonify({"status": "error", "message": f"Invalid file type. Please upload a supported file ({', '.join(allowed_extensions)})."}), 400

    try:
        # --- Save Uploaded File Securely ---
        file_token = secrets.token_urlsafe(8)
        safe_original_filename = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in os.path.splitext(original_filename)[0])[:20]
        # Use a generic temp name or include token
        temp_filename = f"upload_{file_token}_{safe_original_filename}{file_ext}"
        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
        file.save(temp_filepath)
        logging.info(f"File saved temporarily to {temp_filepath}")

        # --- Extract Form Data & Validate ---
        voice = request.form.get('voice')
        stability_str = request.form.get('stability', '0.7') # Default if missing

        if not voice:
             raise ValueError("Voice selection is missing from the request.")
        try:
            stability = float(stability_str)
            if not (0.0 <= stability <= 1.0):
                 raise ValueError("Stability value must be between 0.0 and 1.0.")
        except (ValueError, TypeError):
             logging.warning(f"Invalid stability value: '{stability_str}'")
             raise ValueError("Invalid numeric value provided for Stability.")

        # --- Step 1: Extract Text ---
        logging.info("Starting text extraction...")
        # Adapt this part significantly if EPUB support is added
        extracted_text = extract_text_from_pdf(temp_filepath)
        text_length = len(extracted_text)
        if not extracted_text or not extracted_text.strip():
            logging.warning(f"No text could be extracted from file '{original_filename}'.")
            raise ValueError("Could not extract any text from the file. It might be image-based, empty, or protected.")

        # --- Step 2: Generate Audio ---
        logging.info("Starting audio generation...")
        audio_token = secrets.token_urlsafe(8)
        safe_voice_name = "".join(c if c.isalnum() else "_" for c in voice)[:15]
        audio_filename = f"{safe_original_filename}_{safe_voice_name}_{audio_token}.mp3"
        output_filepath = os.path.join(app.config['AUDIO_FOLDER'], audio_filename)

        # Pass default similarity for now
        text_to_elevenlabs_audio(extracted_text, voice, stability, 0.75, output_filepath)

        # --- Success ---
        processing_time = round(time.time() - start_time, 2)
        logging.info(f"Processing successful in {processing_time}s for '{original_filename}'. Audio: {audio_filename}")

        # --- Return Response ---
        audio_url = f"/audio/{audio_filename}"
        return jsonify({
            "status": "success",
            "message": "Audio generated successfully!",
            "audio_url": audio_url
        })

    # --- Handle Specific Expected Errors ---
    except ValueError as e:
        logging.warning(f"Value error during processing '{original_filename}': {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except PermissionError as e:
        logging.error(f"Permission error during processing '{original_filename}': {e}")
        return jsonify({"status": "error", "message": f"Permission Denied: {e}"}), 403
    except ConnectionError as e:
        logging.error(f"Connection error during processing '{original_filename}': {e}")
        return jsonify({"status": "error", "message": f"Connection Error: {e}"}), 503
    except RuntimeError as e:
         logging.error(f"Runtime error during processing '{original_filename}': {e}", exc_info=True)
         return jsonify({"status": "error", "message": f"Server Runtime Error: {e}"}), 500
    except Exception as e:
        logging.error(f"Unexpected critical error during processing for '{original_filename}': {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An unexpected server error occurred. Please check logs."}), 500
    # --- Cleanup Uploaded File ---
    finally:
        if temp_filepath and os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
                logging.info(f"Removed temporary file: {temp_filepath}")
            except OSError as e:
                logging.warning(f"Could not remove temporary file {temp_filepath}: {e}")


@app.route('/audio/<path:filename>')
def serve_audio(filename):
    """Serves the generated audio files."""
    logging.debug(f"Request received for audio file: {filename}")
    if '..' in filename or filename.startswith('/'):
        logging.warning(f"Attempted directory traversal detected: {filename}")
        return "Invalid filename", 400
    try:
        return send_from_directory(
            directory=app.config['AUDIO_FOLDER'],
            path=filename,
            as_attachment=False
        )
    except FileNotFoundError:
        logging.error(f"Audio file not found: {filename} in {app.config['AUDIO_FOLDER']}")
        return "File not found", 404
    except Exception as e:
        logging.error(f"Error serving audio file {filename}: {e}", exc_info=True)
        return "Error serving file", 500


# --- Run the Flask App ---
if __name__ == '__main__':
    # Check ElevenLabs client status
    if not client and "ELEVENLABS_API_KEY not found" in (VOICE_FETCH_ERROR or ""):
         print("\n" + "="*60)
         print("!! FATAL: ELEVENLABS_API_KEY not found in .env file !!")
         # ... (rest of fatal error message) ...
         import sys
         sys.exit(1)
    elif not client:
         print("\n" + "="*60)
         print("!! WARNING: ElevenLabs client failed to initialize !!")
         # ... (rest of warning message) ...
    elif VOICE_FETCH_ERROR:
         print("\n" + "="*60)
         print("!! WARNING: Failed to fetch ElevenLabs voices on startup !!")
         # ... (rest of warning message) ...

    app.run(debug=True, host='127.0.0.1', port=5001)
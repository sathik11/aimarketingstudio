import os
import logging
import mimetypes

from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from config import AUDIO_OUTPUT_DIR, VIDEO_OUTPUT_DIR
from db import init_db

os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)
os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, static_folder="frontend/dist", static_url_path="")
CORS(app, supports_credentials=True)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "bdo-voice-studio-dev-key-change-in-prod")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True

# Register blueprints
from routes.generate import generate_bp
from routes.scripts import scripts_bp
from routes.voices import voices_bp
from routes.auth_routes import auth_bp
from routes.settings import settings_bp
from routes.video import video_bp
from routes.assets import assets_bp

app.register_blueprint(generate_bp)
app.register_blueprint(scripts_bp)
app.register_blueprint(voices_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(video_bp)
app.register_blueprint(assets_bp)

# Initialize database
init_db()


# --- Core routes ---

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


@app.route('/audio/<path:filename>', methods=['GET'])
def serve_audio(filename):
    # Determine mimetype from extension
    mt, _ = mimetypes.guess_type(filename)
    return send_from_directory(AUDIO_OUTPUT_DIR, filename, mimetype=mt or "audio/wav")


# --- Legacy endpoint (backward compat) ---

@app.route('/taglishtranslator', methods=['POST'])
def taglishtranslator():
    logging.info('Legacy /taglishtranslator endpoint called.')
    from translate_ssml import taglish_translate

    try:
        req_body = request.get_json()
        eng_text = req_body['englishtext']
        taglish_res = taglish_translate(eng_text)
    except (ValueError, KeyError) as e:
        logging.error(f"Error processing request: {e}")
        return jsonify({"error": "Invalid input"}), 400
    except Exception as e:
        logging.exception("Unhandled error during translation request")
        return jsonify({"error": str(e)}), 500

    if taglish_res:
        local_audio_file = taglish_res.get("local_audio_file")
        if local_audio_file:
            local_audio_url = url_for("serve_audio", filename=local_audio_file, _external=True)
            taglish_res["local_audio_url"] = local_audio_url
            if not taglish_res.get("storage_url"):
                taglish_res["speech_output"] = local_audio_url
        return jsonify(taglish_res), 200
    else:
        return jsonify({"message": "No result"}), 200


# --- Serve React frontend (catch-all) ---

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path and os.path.exists(os.path.join(app.static_folder or "", path)):
        return send_from_directory(app.static_folder, path)
    index_path = os.path.join(app.static_folder or "", "index.html")
    if os.path.exists(index_path):
        return send_from_directory(app.static_folder, "index.html")
    return jsonify({"status": "ok", "message": "BDO TTS API. Frontend not built yet."}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
import os
import logging
import mimetypes
import signal
import atexit

from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from config import AUDIO_OUTPUT_DIR
from db import init_db
from services.blob_sync import restore_from_blob, upload_db_to_blob, force_upload_db_to_blob

os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "bdo-voice-studio-secret-key-2026")
CORS(app)

logger = logging.getLogger(__name__)

# Register blueprints
from routes.generate import generate_bp
from routes.scripts import scripts_bp
from routes.voices import voices_bp
from routes.auth_routes import auth_bp
from routes.video import video_bp
from routes.assets import assets_bp
from routes.settings import settings_bp

app.register_blueprint(generate_bp)
app.register_blueprint(scripts_bp)
app.register_blueprint(voices_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(video_bp)
app.register_blueprint(assets_bp)
app.register_blueprint(settings_bp)

# Restore DB and audio from blob storage, then init DB
restore_from_blob()
init_db()


# Ensure DB is synced to blob on graceful shutdown
def _shutdown_sync(*args):
    logger.info("Shutdown: force-syncing DB to blob storage...")
    force_upload_db_to_blob()

atexit.register(_shutdown_sync)
signal.signal(signal.SIGTERM, lambda sig, frame: (_shutdown_sync(), exit(0)))


# Sync DB to blob after every mutating request
@app.after_request
def sync_db_after_write(response):
    if request.method in ("POST", "PUT", "DELETE", "PATCH") and response.status_code < 500:
        upload_db_to_blob()
    return response


# --- Core routes ---

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200


@app.route('/audio/<path:filename>', methods=['GET'])
def serve_audio(filename):
    # On-demand download from blob if not local
    from services.blob_sync import download_audio_file_on_demand
    if not download_audio_file_on_demand(filename):
        return jsonify({"error": "Audio file not found"}), 404
    mt, _ = mimetypes.guess_type(filename)
    return send_from_directory(AUDIO_OUTPUT_DIR, filename, mimetype=mt or "audio/wav")


# --- Serve React frontend (catch-all) ---

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    if path:
        full = os.path.join(FRONTEND_DIR, path)
        if os.path.isfile(full):
            return send_from_directory(FRONTEND_DIR, path)
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({"status": "ok", "message": "BDO TTS API. Frontend not built yet."}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
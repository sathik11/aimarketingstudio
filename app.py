import os
import logging
import mimetypes

from flask import Flask, request, jsonify, send_from_directory, url_for
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from config import AUDIO_OUTPUT_DIR
from db import init_db

os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, static_folder="frontend/dist", static_url_path="")
CORS(app)

# Register blueprints
from routes.generate import generate_bp
from routes.scripts import scripts_bp
from routes.voices import voices_bp
from routes.auth_routes import auth_bp

app.register_blueprint(generate_bp)
app.register_blueprint(scripts_bp)
app.register_blueprint(voices_bp)
app.register_blueprint(auth_bp)

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
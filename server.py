import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Lecture de la liste d'utilisateurs autorisés depuis la variable d'environnement
# Format attendu : "Tarik,Ayoub,Sara"
AUTHORIZED_ENV = os.getenv("AUTHORIZED_USERS", "")
if AUTHORIZED_ENV:
    AUTHORIZED_USERS = [u.strip() for u in AUTHORIZED_ENV.split(",") if u.strip()]
else:
    # fallback : liste par défaut (utile pour tests)
    AUTHORIZED_USERS = ["Tarik", "Ayoub", "Sara"]

@app.route("/")
def index():
    return {"status": "ok", "message": "Auth server running"}, 200

@app.route("/auth", methods=["POST"])
def auth():
    # on attend un JSON : {"username": "Tarik"}
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    if not username:
        return jsonify({"error": "username missing"}), 400

    if username in AUTHORIZED_USERS:
        return jsonify({"authorized": True, "message": "Utilisateur autorisé ✅"}), 200
    else:
        return jsonify({"authorized": False, "message": "Accès refusé ❌"}), 403

# Healthcheck (Render peut utiliser /)
@app.route("/health")
def health():
    return {"alive": True}, 200

if __name__ == "__main__":
    # pour dev local seulement
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

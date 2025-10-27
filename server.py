from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import datetime

app = Flask(__name__)
CORS(app)

DATA_FILE = "data.json"

# === Fonctions utilitaires ===
def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def calc_expiry(duration):
    now = datetime.datetime.now()
    if duration == "1w":
        return (now + datetime.timedelta(weeks=1)).isoformat()
    elif duration == "2w":
        return (now + datetime.timedelta(weeks=2)).isoformat()
    elif duration == "1m":
        return (now + datetime.timedelta(days=30)).isoformat()
    elif duration == "3m":
        return (now + datetime.timedelta(days=90)).isoformat()
    elif duration == "6m":
        return (now + datetime.timedelta(days=180)).isoformat()
    elif duration == "1y":
        return (now + datetime.timedelta(days=365)).isoformat()
    else:
        return None  # Illimité


# === Routes ===
@app.route("/set", methods=["POST"])
def set_user():
    data = load_data()
    body = request.json
    username = body.get("username")
    duration = body.get("duration")

    if not username:
        return jsonify({"error": "Missing username"}), 400

    expiry = calc_expiry(duration)
    data[username] = {"expiry": expiry}
    save_data(data)

    return jsonify({"message": f"{username} ajouté avec durée {duration or 'illimitée'}."})


@app.route("/get", methods=["GET"])
def get_users():
    data = load_data()
    now = datetime.datetime.now()

    for user, info in list(data.items()):
        expiry = info.get("expiry")
        if expiry:
            expiry_date = datetime.datetime.fromisoformat(expiry)
            if expiry_date < now:
                del data[user]

    save_data(data)
    return jsonify(data)


@app.route("/remove", methods=["POST"])
def remove_user():
    data = load_data()
    username = request.json.get("username")

    if username in data:
        del data[username]
        save_data(data)
        return jsonify({"message": f"{username} supprimé."})
    else:
        return jsonify({"error": "Utilisateur introuvable."}), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

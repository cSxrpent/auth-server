from flask import Flask, request, jsonify

app = Flask(__name__)

# Liste d'utilisateurs autorisés
authorized_users = ["Tarik", "Ahmet", "Selim"]

@app.route('/')
def home():
    return "Auth server is running."

@app.route('/auth', methods=['GET'])
def auth():
    username = request.args.get('username')
    if not username:
        return jsonify({"error": "username parameter is missing"}), 400

    if username in authorized_users:
        return jsonify({"status": "authorized"})
    else:
        return jsonify({"status": "unauthorized"}), 403

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=10000)

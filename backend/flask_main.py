# flask_main.pyの修正
from flask import Flask, request, jsonify
from flask_cors import CORS
from firebase_admin import auth, credentials, initialize_app

app = Flask(__name__)
# CORSの設定を開発環境用に変更
CORS(app, origins=["http://localhost:5173"], supports_credentials=True)

@app.route("/app/login", methods=["POST"])
def login():
    try:
        # AuthorizationヘッダーからFirebaseトークンを取得
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "トークンがありません"}), 401
            
        token = auth_header.split("Bearer ")[1]
        
        # Firebaseトークンを検証
        decoded_token = auth.verify_id_token(token)
        user_email = decoded_token.get("email", "Unknown User")
        
        # ログイン成功のレスポンス
        return jsonify({
            "status": "success",
            "user": {
                "email": user_email
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 401

@app.route("/app/logout", methods=["POST"])
def logout():
    try:
        return jsonify({
            "status": "success",
            "message": "Logged out successfully"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 401

if __name__ == "__main__":
    app.run(port=8080)



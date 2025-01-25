# flask_main.pyの修正
from flask import Flask, request, jsonify, make_response, Response
from flask_cors import CORS
import firebase_admin
from firebase_admin import auth, credentials, initialize_app
import logging
# ロギングの設定
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log")],
)
logger = logging.getLogger(__name__)

# Initialize Firebase Admin with your service account credentials
cred = credentials.Certificate("config/serviceaccount_marine-lane-20190317-1192-f9d21eda3011.json")
firebase_admin.initialize_app(cred)


app = Flask(__name__)
CORS(app, 
     origins=["http://localhost:5173"], 
     supports_credentials=True,
     expose_headers=["Authorization"],
     allow_headers=["Content-Type", "Authorization"])

def get_token_from_request():
    """リクエストからトークンを取得する関数"""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split("Bearer ")[1]
    return request.cookies.get('access_token')

@app.route("/app/login", methods=["POST"])
def login():
    try:
        token = get_token_from_request()
        if not token:
            return jsonify({"error": "トークンがありません"}), 401
        
        decoded_token = auth.verify_id_token(token)
        user_email = decoded_token.get("email", "Unknown User")
        
        response = make_response(jsonify({
            "status": "success",
            "user": {"email": user_email}
        }))
        
        response.set_cookie(
            'access_token',
            token,
            httponly=True,
            secure=True,
            samesite='Strict',
            max_age=3600,
            path='/'
        )
        
        return response
        
    except Exception as e:
        return jsonify({"error": str(e)}), 401

@app.route("/app/logout", methods=["POST"])
def logout():
    try:
        response = make_response(jsonify({
            "status": "success",
            "message": "Logged out successfully"
        }))
        response.delete_cookie('access_token')
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 401

@app.route("/app/verify-auth", methods=["GET"])
def verify_auth():
    try:
        logger.info("Verify auth request received")
        token = get_token_from_request()
        if not token:
            logger.warning("No token found in request")
            return jsonify({"error": "認証が必要です"}), 401
            
        logger.info(f"Token received: {token[:10]}...")
        decoded_token = auth.verify_id_token(token)
        logger.info(f"Token successfully decoded for user: {decoded_token.get('email')}")
        
        response_data = {
            "status": "success", 
            "user": {
                "email": decoded_token.get("email"),
                "uid": decoded_token.get("uid")
            }
        }
        logger.info(f"Sending successful response: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 401

app.run(port=8080)
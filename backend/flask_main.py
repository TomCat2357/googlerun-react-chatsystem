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
        ret_token = auth_header.split("Bearer ")[1]
        logger.info('Token getted from request headers: %s', ret_token[:10])
    else:
        ret_token = request.cookies.get('access_token')
        logger.info('Token getted from cookies: %s', ret_token[:10])
    return ret_token

@app.route("/app/verify-auth", methods=["GET"])
def verify_auth():
    try:
        logger.info("Request headers: %s", request.headers)
        
        token = get_token_from_request()
        if not token:
            logger.warning("No token found in request")
            return jsonify({"error": "認証が必要です"}), 401
            
        logger.info("Token received: %s...", token[:10])
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=60)
        logger.info("Token successfully decoded for user: %s", decoded_token.get('email'))
        
        response_data = {
            "status": "success", 
            "user": {
                "email": decoded_token.get("email"),
                "uid": decoded_token.get("uid")
            }
        }

        # レスポンスを作成し、クッキーを設定
        response = make_response(jsonify(response_data))
        response.set_cookie(
            'access_token',
            token,
            httponly=True,
            secure=True,
            samesite='Strict',
            max_age=3600,
            path='/'
        )
        
        logger.info("Sending successful response: %s", response_data)
        return response

    except Exception as e:
        logger.error("Authentication error: %s", str(e), exc_info=True)
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

if  __name__ == "__main__":
    app.run(port=8080)  
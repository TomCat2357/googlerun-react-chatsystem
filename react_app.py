from flask import Flask, send_from_directory

app = Flask(__name__)
base_path = './frontend/dist'

@app.route('/')
def index():
    return send_from_directory(base_path, 'index.html')

@app.route('/<path:path>')
def static_file(path):
    return send_from_directory(base_path, path)

if __name__ == '__main__':
    app.run()
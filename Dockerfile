FROM python:3.11-slim

WORKDIR /app
COPY ./app .
RUN pip install --no-cache-dir -r ./config/requirements.txt

CMD ["sh", "-c", "exec gunicorn --bind :$PORT --workers 1 --timeout 0 flask_main:app"]
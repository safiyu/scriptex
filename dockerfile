FROM python:3.9-alpine
WORKDIR /app
RUN pip install flask gunicorn
RUN apk add --no-cache bash curl jq coreutils
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "webserver:app", "--workers", "4", "--timeout", "120", "--keep-alive", "5", "--log-level", "info"]
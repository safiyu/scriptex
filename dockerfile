FROM python:3.9-alpine
WORKDIR /app
RUN pip install flask gunicorn
RUN apk add --no-cache bash curl jq
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:5100", "webserver:app"]
FROM python:3.9.15

COPY ./src /app/src
COPY ./requirements.txt /app

WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app/src

entrypoint uvicorn main:app --host 0.0.0.0 --port 3333
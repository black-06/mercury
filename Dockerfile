FROM python:3.9.15

WORKDIR /app

COPY ./requirements.txt /app/

RUN pip config set global.index-url https://mirrors.tencentyun.com/pypi/simple && \
    pip install --no-cache-dir -r requirements.txt

WORKDIR /app/src

COPY ./src /app/src

entrypoint uvicorn main:app --host 0.0.0.0 --port 3333
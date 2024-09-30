FROM python:3.10.14

WORKDIR /app/azure

COPY ./requirements.txt /app/azure

RUN pip config set global.index-url https://repo.huaweicloud.com/repository/pypi/simple && \
    pip config set global.trusted-host repo.huaweicloud.com && \
    pip config set global.timeout 120 && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

COPY ./azure_celery.py /app/azure/azure_celery.py

CMD celery -A azure_celery worker --loglevel=INFO -Q azure_infer
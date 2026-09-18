FROM python:3.12-slim
RUN pip install --no-cache-dir gunicorn==23.0.0 && useradd --uid 10001 --create-home trainer
WORKDIR /app
COPY gateway/cloud_service.py gateway/cloud_schema.py /app/
RUN mkdir /data && chown trainer:trainer /data
USER trainer
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "40", "cloud_service:create_app()"]

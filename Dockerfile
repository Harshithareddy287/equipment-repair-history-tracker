FROM python:3.12.7-slim
WORKDIR /app
COPY pyproject.toml ./
COPY service_tracker ./service_tracker
RUN pip install --no-cache-dir .
COPY data ./data
RUN useradd --create-home app && mkdir /data && chown app:app /data
USER app
ENV SERVICE_DB_PATH=/data/service.db
VOLUME ["/data"]
ENTRYPOINT ["service-tracker"]
CMD ["--version"]

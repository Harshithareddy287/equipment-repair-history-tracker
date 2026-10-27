FROM python:3.12.7-slim
WORKDIR /app
COPY pyproject.toml ./
COPY service_tracker ./service_tracker
RUN pip install --no-cache-dir .
COPY data ./sample_data
RUN useradd --create-home app && mkdir /data && chown app:app /data
USER app
ENV SERVICE_DB_PATH=/data/service.db
VOLUME ["/data"]
ENTRYPOINT ["service-tracker"]
CMD ["run", "--visits", "sample_data/visits.csv", "--stock", "sample_data/stock.csv", "--settings", "sample_data/settings.json"]

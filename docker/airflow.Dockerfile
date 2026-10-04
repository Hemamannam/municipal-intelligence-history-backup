# Airflow image with the platform installed, so DAG tasks import
# ingestion/normalization/entity_resolution directly.
FROM apache/airflow:2.10.4-python3.12

USER root
RUN mkdir -p /opt/mip && chown -R 50000:0 /opt/mip
USER airflow

# Project source (ingestion, normalization, ER, dbt project, scripts).
COPY --chown=50000:0 pyproject.toml /opt/mip/
COPY --chown=50000:0 ingestion /opt/mip/ingestion
COPY --chown=50000:0 normalization /opt/mip/normalization
COPY --chown=50000:0 entity_resolution /opt/mip/entity_resolution
COPY --chown=50000:0 scripts /opt/mip/scripts
COPY --chown=50000:0 dbt /opt/mip/dbt

RUN pip install --no-cache-dir -e /opt/mip "dbt-duckdb>=1.8"

WORKDIR /opt/mip

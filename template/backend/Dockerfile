FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt ./
COPY runtime.py /opt/foundry/runtime.py
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 1000 --create-home appuser
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
USER 1000:1000
EXPOSE 8000
CMD ["python", "/opt/foundry/runtime.py"]

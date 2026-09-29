FROM FOUNDRY_API_IMAGE
COPY --chown=1000:1000 app /app/app
COPY --chown=1000:1000 migrations /app/migrations
COPY runtime.py /opt/foundry/runtime.py
USER 1000:1000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-proxy-headers", "--no-access-log", "--limit-concurrency", "40", "--timeout-keep-alive", "5"]

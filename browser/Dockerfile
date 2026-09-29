FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
RUN pip install --no-cache-dir --only-binary=:all: playwright==1.63.0
COPY runner.py /opt/foundry/browser.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER pwuser
ENTRYPOINT ["python", "/opt/foundry/browser.py"]

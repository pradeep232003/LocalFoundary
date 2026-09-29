FROM FOUNDRY_API_IMAGE
COPY --chown=1000:1000 proxy.py /opt/foundry/proxy.py
USER 1000:1000
CMD ["python", "-u", "/opt/foundry/proxy.py"]

FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard.py .
COPY static ./static

EXPOSE 8090
CMD ["python", "dashboard.py"]

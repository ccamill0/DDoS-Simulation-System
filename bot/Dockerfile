FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

EXPOSE 7000
CMD ["python", "bot.py"]

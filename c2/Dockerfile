FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY c2.py .

EXPOSE 9000/udp 9001 9002 9003
CMD ["python", "c2.py"]

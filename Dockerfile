FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8010

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY docs ./docs
COPY db ./db
COPY scripts ./scripts
COPY README.md package.json ./

EXPOSE 8010

CMD ["python", "backend/server.py"]

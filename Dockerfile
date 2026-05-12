FROM python:3.11-slim

# System deps: FFmpeg + build tools for OpenCV / Librosa
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 libxext6 libgl1 \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/backend/

ENV PYTHONPATH=/app/backend
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

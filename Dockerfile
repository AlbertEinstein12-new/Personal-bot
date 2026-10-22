FROM node:20-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY main.py .
ENV PATH="/opt/venv/bin:$PATH"
RUN python main.py --setup

CMD ["python", "main.py"]

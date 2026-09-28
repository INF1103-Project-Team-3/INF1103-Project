# FROM python:3.11-slim

# # Force Python logs to output immediately without buffering
# ENV PYTHONUNBUFFERED=1

# # 1. Set working directory strictly to /data
# WORKDIR /data

# # 2. Copy data_manager.py directly into /data
# COPY data_manager.py feedback_store.json .

# # 3. Execute script from /data
# CMD ["python", "/data/data_manager.py"]

FROM python:3.11-slim

# Force Python logs to stream directly to terminal output
ENV PYTHONUNBUFFERED=1

# 1. Set application code directory to /app
WORKDIR /app

# 2. Pre-create mount point for persistent dataset volume
RUN mkdir -p /data

# 3. Copy python script into /app
COPY data_manager1.py /app/data_manager1.py

# 4. Execute script from /app pointing to /data volume
CMD ["python", "/app/data_manager1.py", "/data/feedback_store.json"]
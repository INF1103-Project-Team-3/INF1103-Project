FROM python:3.11-slim

WORKDIR /app

# Pre-create the directory where persistent data will live
RUN mkdir -p /app/data

# Copy your Python script into the container
COPY data_manager.py .

# Run the Data Manager script
CMD ["python", "data_manager.py"]
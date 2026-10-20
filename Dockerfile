FROM python:3.11-slim

# Show output straight away and don't write .pyc files into the repo
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The repo root lives at /Project inside the container
WORKDIR /Project

# Install dependencies first, so this step is cached until requirements.txt changes.
# pytest is included so the tests in the README can run inside the container.
COPY requirements/requirements.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/requirements.txt pytest

# Copy the repo into the image (.dockerignore keeps out .env, .git and caches)
COPY . .

# data_manager saves to /data: point that at the repo's own data/ folder,
# so every file the app writes ends up in data/ in the repo
RUN ln -s /Project/data /data

# Run the app from the repo root (data/ is created if it's missing)
CMD ["sh", "-c", "mkdir -p data && python managers/main.py"]

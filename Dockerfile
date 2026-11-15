FROM python:3.11-slim-bookworm

# Show output straight away and don't write .pyc files into the repo
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The repo root lives at /Project inside the container
WORKDIR /Project

# System libraries Qt (PySide6) needs to draw the GUI, plus a font, plus noVNC and
# websockify, which show the GUI in a web browser (service "gui" in docker-compose.yml).
# Pinned to Debian bookworm so these package names don't change under us.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1 libegl1 libx11-6 libxkbcommon0 libglib2.0-0 libfontconfig1 \
      libdbus-1-3 libgssapi-krb5-2 fonts-dejavu-core \
      novnc websockify \
 && rm -rf /var/lib/apt/lists/*

# The page at http://localhost:6080/ that shows the GUI full-window (docker/gui/index.html)
COPY docker/gui/index.html /usr/share/novnc/index.html

# Install dependencies first, so this step is cached until a requirements file changes.
# gui.txt adds PySide6 and pytest-qt, so the GUI runs and its tests run in CI too.
COPY requirements/ ./requirements/
RUN pip install --no-cache-dir -r requirements/requirements.txt -r requirements/gui.txt pytest

# Copy the repo into the image (.dockerignore keeps out .env, .git and caches)
COPY . .

# data_manager saves to /data: point that at the repo's own data/ folder,
# so every file the app writes ends up in data/ in the repo
RUN ln -s /Project/data /data

# Terminal mode by default; the "gui" service in docker-compose.yml starts the GUI instead
CMD ["python", "-m", "managers.main"]

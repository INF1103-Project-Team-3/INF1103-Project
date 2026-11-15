FROM python:3.11-slim-bookworm

# Show output straight away and don't write .pyc files into the repo
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# The repo root lives at /Project inside the container
WORKDIR /Project

# System packages for the GUI (service "gui" in docker-compose.yml), pinned to
# Debian bookworm so these package names don't change under us:
#   - libraries Qt (PySide6) needs to draw on an X11 screen, plus a font
#   - xvfb (a virtual screen), matchbox-window-manager (keeps the window full-screen)
#     and x11vnc (shares that screen)
#   - novnc and websockify, which show the shared screen in a web browser
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libgl1 libegl1 libx11-6 libx11-xcb1 libxkbcommon0 libxkbcommon-x11-0 \
      libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
      libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
      libglib2.0-0 libfontconfig1 libdbus-1-3 libgssapi-krb5-2 fonts-dejavu-core \
      xvfb matchbox-window-manager x11vnc \
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

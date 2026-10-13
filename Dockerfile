FROM python:3.11-slim

# Set the working directory to the root of the container
WORKDIR /

# 1. Copy the requirements file into the matching container directory structure
COPY INF1103-Project-main/requirements/requirements.txt ./INF1103-Project-main/requirements/

# 2. Run pip using the internal container path
RUN pip install --no-cache-dir -r INF1103-Project-main/requirements/requirements.txt

# 3. Copy all project contents into the matching container directory
COPY INF1103-Project-main/ ./INF1103-Project-main/

# 4. Set the working directory to the new matching path
WORKDIR /INF1103-Project-main

# Run your main script
CMD ["python", "Managers/main.py"]



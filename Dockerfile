FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /Project

# Copy requirements from the local Project subfolder
COPY Project/Requirements/requirements.txt ./Requirements/

# Install dependencies
RUN pip install --no-cache-dir -r Requirements/requirements.txt

# Copy the contents of your local Project folder into the container's working directory
COPY Project/ .

# Run your main script
CMD ["python", "Managers/main.py"]


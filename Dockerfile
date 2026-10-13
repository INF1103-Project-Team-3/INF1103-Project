FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /Project

# Copy requirements from the local Project subfolder
COPY requirements/requirements.txt ./requirements/

# Install dependencies
RUN pip install --no-cache-dir -r requirements/requirements.txt

# Copy the contents of your local Project folder into the container's working directory
COPY . .

# Run your main script
CMD ["python", "managers/main.py"]


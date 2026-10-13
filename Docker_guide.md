# Docker Compose guide

Quick reference guide for managing the Docker environment.

## Commands

### 1. Build and Run Containers
Build the images and start the containers in the foreground (run command in terminal and at root of folder):
```bash
docker compose up --build
```

### 2. Stop Containers
Stop and remove the containers, networks, and volumes created by `up`(run command in terminal and at root of folder):
```bash
docker compose down
```

### 3. Run Application Script
Execute the main script inside the running `app` container(run command in terminal and at root of folder):
```bash
docker compose exec app python Managers/main.py
```

### 4. Access Container Shell
Open an interactive shell session inside the running `app` container(run command in terminal and at root of folder):
```bash
docker compose exec app sh
```

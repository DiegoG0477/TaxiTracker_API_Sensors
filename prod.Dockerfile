# Dockerfile for production
FROM python:3.12-slim-bookworm

WORKDIR /app

# Copy only the requirements file first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Copy the local.env file into the container
COPY local.env .env

# Use environment variables from .env file
ENV $(cat .env | xargs)
ENV PORT 8080

EXPOSE 8080

# Install Supervisor
RUN apt-get update && apt-get install -y supervisor

# Copy supervisor configuration file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Command to run Supervisor
CMD ["/usr/bin/supervisord"]
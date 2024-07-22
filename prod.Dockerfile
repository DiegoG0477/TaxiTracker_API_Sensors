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

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# uvicorn main:app --host 0.0.0.0 --port 8080
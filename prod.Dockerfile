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

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
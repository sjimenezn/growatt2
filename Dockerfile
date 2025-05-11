# Use a base image that has Python and Chromium
FROM python:3.9-slim

# Install dependencies
RUN apt-get update && \
    apt-get install -y \
    wget \
    curl \
    chromium \
    chromium-driver \
    libgsf-1-114 \
    libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Set environment variable to make sure Chrome runs headless
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROMEDRIVER_BIN=/usr/bin/chromium-driver

# Create app directory
WORKDIR /app

# Copy the application files into the container
COPY . .

# Expose the app on port 8000
EXPOSE 8000

# Command to run the Flask app
CMD ["python", "main.py"]
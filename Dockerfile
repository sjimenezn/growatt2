FROM python:3.9-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    fonts-liberation \
    wget \
    unzip \
    curl \
    gnupg \
    libnss3 \
    libxss1 \
    libasound2 \
    libx11-xcb1 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV CHROME_BIN=/usr/bin/chromium \
    PATH=$PATH:/usr/bin

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Expose Flask port
EXPOSE 8000

# Start the app
CMD ["python", "main.py"]
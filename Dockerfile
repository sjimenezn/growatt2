# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies including curl, unzip, and ffmpeg
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    curl \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (JavaScript runtime for yt-dlp)
RUN curl -fsSL https://deno.land/install.sh | sh

# Set Deno environment variables
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

# Copy the current directory contents into the container at /app
COPY . /app

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the necessary port
EXPOSE 3000

# Run the Flask app when the container starts
CMD ["python", "main.py"]

# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies including ffmpeg and deno (JavaScript runtime)
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (JavaScript runtime for yt-dlp)
RUN wget -qO- https://deno.land/install.sh | sh && \
    export DENO_INSTALL="/root/.deno" && \
    export PATH="$DENO_INSTALL/bin:$PATH" && \
    echo 'export PATH="$DENO_INSTALL/bin:$PATH"' >> /root/.bashrc

# Copy the current directory contents into the container at /app
COPY . /app

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the necessary port
EXPOSE 3000

# Set PATH to include deno
ENV PATH="/root/.deno/bin:${PATH}"

# Run the Flask app when the container starts
CMD ["python", "main.py"]

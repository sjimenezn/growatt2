# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (for requests and git)
RUN apt-get update && apt-get install -y git

# Copy the current directory contents into the container at /app
COPY . /app

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose the necessary port (Koyeb default is 80, but we use 3000 as per your script)
EXPOSE 3000

# Run the Flask app when the container starts
CMD ["python", "main.py"]

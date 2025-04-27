# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install git to clone dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements.txt file into the container at /app
COPY requirements.txt .

# Install any dependencies from requirements.txt
RUN pip install -r requirements.txt

# Copy the rest of your application files
COPY . .

# Command to run your application (replace with your actual entry point)
CMD ["python", "your_script.py"]

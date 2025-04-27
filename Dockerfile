# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Install git to clone dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Add GitHub token as an environment variable
ENV GITHUB_TOKEN=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

# Copy the requirements.txt file into the container at /app
COPY requirements.txt .

# Modify the repository URL in requirements.txt to use the token
RUN sed -i 's|git+https://github.com/jjskuld/growattServer.git|git+https://$GITHUB_TOKEN@github.com/jjskuld/growattServer.git|' requirements.txt

# Install any dependencies from requirements.txt
RUN pip install -r requirements.txt

# Copy the rest of your application files
COPY . .

# Command to run your application (replace with your actual entry point)
CMD ["python", "your_script.py"]

# Use official Python runtime as a parent image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the ports for FastAPI and Streamlit
EXPOSE 8000
EXPOSE 8501

# Command to run both using our run script
CMD ["python", "run_all.py"]

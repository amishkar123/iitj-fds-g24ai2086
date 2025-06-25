# Use official Python image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy test script
COPY test.py .

# Run the tests (with delay to allow services to start)
CMD ["sh", "-c", "sleep 10 && python test.py"]
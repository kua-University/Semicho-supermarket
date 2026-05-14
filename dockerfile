# Use a lightweight Python image
FROM python:3.10-slim

# Set the working directory inside the container
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set environment variable for the database path
# Using /app/data ensures the DB persists if we mount a volume
ENV SEMICHO_DB_PATH=/app/data/supermarket.db

# Expose the Flask port
EXPOSE 5000

# Run the application using Gunicorn (production-grade server)
RUN pip install gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
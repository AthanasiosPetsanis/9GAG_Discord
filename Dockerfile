FROM python:3.11-slim

# Install ffmpeg
RUN apt update && apt install -y ffmpeg

# Create and use working directory
WORKDIR /app

# Copy everything into the container
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose Flask port
EXPOSE 8080
ENV PORT=8080

# Run the app
CMD ["python", "main.py"]

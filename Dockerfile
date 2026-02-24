FROM python:3.11-slim

# Встановлюємо ffmpeg (для музики) та інші системні залежності
RUN apt-get update && \
    apt-get install -y ffmpeg libffi-dev libnacl-dev python3-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Робоча директорія
WORKDIR /app

# Копіюємо список залежностей і встановлюємо їх
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо всі файли бота
COPY . .

# Команда для запуску
CMD ["python", "main.py"]

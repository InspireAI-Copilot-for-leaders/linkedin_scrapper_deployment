FROM python:3.11

# Install dependencies
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    xvfb \
    libxi6 \
    libgconf-2-4 \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome version 128
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
    && apt-get update \
    && apt-get install -y google-chrome-stable=128.0.6613.138\
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver for Chrome 128
RUN wget -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/128.0.6613.138/chromedriver_linux64.zip \
    && unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip

# Set display port to avoid crash
ENV DISPLAY=:99

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r /app/requirements.txt

CMD ["python", "/app/main.py"]

FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .

ENV FLASK_APP=node.py
ENV FLASK_ENV=production

CMD ["flask", "run", "--host=0.0.0.0"]
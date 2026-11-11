FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8765 \
    DATABASE_PATH=/var/lib/waitlist/waitlist.sqlite3

WORKDIR /app
COPY gmail_assignment/gmail_auto.py /app/gmail_assignment/gmail_auto.py
COPY waitlist_project/server.py /app/waitlist_project/server.py

RUN useradd --system --create-home --home-dir /home/waitlist waitlist \
    && mkdir -p /var/lib/waitlist \
    && chown -R waitlist:waitlist /var/lib/waitlist

USER waitlist
EXPOSE 8765
CMD ["python", "/app/waitlist_project/server.py"]

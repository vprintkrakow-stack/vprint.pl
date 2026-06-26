FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends qpdf && \
    which qpdf && \
    qpdf --version && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=10000
ENV PATH="/usr/local/bin:/usr/bin:/bin:${PATH}"

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000"]
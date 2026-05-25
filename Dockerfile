FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir uv && uv pip install --system -e .

COPY . .
RUN mkdir -p data

CMD ["python", "run.py"]

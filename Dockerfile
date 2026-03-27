FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY market_signals/ market_signals/
COPY static/ static/
RUN pip install --no-cache-dir .

ENV PORT=8080
EXPOSE 8080

CMD python -m market_signals

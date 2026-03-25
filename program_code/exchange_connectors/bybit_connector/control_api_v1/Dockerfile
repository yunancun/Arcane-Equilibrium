FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

RUN mkdir -p /runtime

ENV OPENCLAW_STATE_FILE=/runtime/openclaw_bybit_control_state.json
ENV OPENCLAW_API_TOKEN=change-me

EXPOSE 8710

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8710"]

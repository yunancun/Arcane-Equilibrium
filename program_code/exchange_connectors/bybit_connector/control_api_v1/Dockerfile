FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

RUN mkdir -p /runtime

ENV OPENCLAW_STATE_FILE=/runtime/openclaw_bybit_control_state.json
# Batch B security: container deployments must inject a real token or token file.
# Batch B 安全：容器部署必須注入真實 token 或 token file，禁止不安全占位值。
ENV OPENCLAW_API_TOKEN_STRICT=1

EXPOSE 8710

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8710"]

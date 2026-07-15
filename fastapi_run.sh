#!/bin/bash
# Start the fastapi app locally on the host
export REDIS_HOST=localhost
export RABBITMQ_HOST=localhost
export DATABASE_URL=sqlite:///./simserver_dev.db
uvicorn fastapi_app.webapp:app --reload --port 5001 --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem
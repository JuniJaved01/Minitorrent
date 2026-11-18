# Dockerfile -- OWNER: HAMZA -- one image runs the tracker, a peer or the dashboard
FROM python:3.11-slim
# work inside /app
WORKDIR /app
# install the dependencies first so Docker can cache this layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# copy the project code
COPY . .
# print output immediately
ENV PYTHONUNBUFFERED=1
# default command (docker-compose overrides it per service)
CMD ["python", "-m", "tracker.server"]

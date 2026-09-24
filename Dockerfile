FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY vite.config.js ./
COPY frontend/index.html frontend/index.html
COPY frontend/src frontend/src
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=false
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home app
COPY manage.py gunicorn.conf.py ./
COPY keycafe_tableau keycafe_tableau
COPY keycafe_api keycafe_api
COPY --from=frontend /build/frontend/dist frontend/dist
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--config", "gunicorn.conf.py", "keycafe_tableau.wsgi:application"]

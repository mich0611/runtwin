FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system runtwin && adduser --system --ingroup runtwin runtwin
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/runtime/exports /app/staticfiles && chown -R runtwin:runtwin /app
USER runtwin
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && python manage.py seed_athlete_profile && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2"]

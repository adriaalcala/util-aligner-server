
from celery import Celery

from config import settings


app = Celery('util_aligner')
app.config_from_object(settings.celery)

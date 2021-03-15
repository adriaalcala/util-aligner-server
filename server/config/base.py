import environs
from kombu import Queue

env = environs.Env()

class CelerySettings(object): pass

celery = CelerySettings()

celery.imports = ['main']

celery.broker_url = env('CELERY_BROKER_URL',
                        "amqp://guest:guest@rabbitmq:5672//")
celery.accept_content = {'json'}
celery.timezone = 'Europe/Madrid'
celery.enable_utc = True

celery.worker_redirect_stdouts = False
celery.worker_prefetch_multiplier = 4
celery.worker_max_tasks_per_child = 500

celery.task_ignore_result = True

celery_time_limit = env.int('CELERY_TASK_TIME_LIMIT', None)
if celery_time_limit is not None:
    celery.task_time_limit = celery_task_time_limit
celery.task_acks_late = True

celery.task_default_queue = env('CELERY_TASK_DEFAULT_QUEUE')
celery.task_default_routing_key = celery.task_default_queue
celery.task_default_exchange = 'celery'
celery.task_default_exchange_type = 'direct'

celery.task_queues = [
    Queue(celery.task_default_queue, routing_key=celery.task_default_queue,
          queue_arguments={'x-max-priority': 10})
]


FINISHED_ALIGNMENT_URL = env('FINISHED_ALIGNMENT_URL')
FINISHED_COMPARISON_URL = env('FINISHED_COMPARISON_URL')

SOURCES_API_URL = env('SOURCES_API_URL')

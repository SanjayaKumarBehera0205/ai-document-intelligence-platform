from celery import Celery

from app.config import settings
from app.services import process_document

celery_app = Celery("document_worker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(task_track_started=True, task_serializer="json", result_serializer="json", accept_content=["json"])


@celery_app.task(name="process_document")
def process_document_task(document_id: int) -> None:
    process_document(document_id)

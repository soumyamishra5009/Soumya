from app.workers.celery_app import celery_app
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="extract_action_items")
def extract_action_items_task(transcript_text: str, meeting_id: str = None):
    """
    Extract action items, decisions, deadlines from transcript
    Uses structured LLM output (JSON schema)
    Will be implemented in Phase 1
    """
    logger.info(f"Extracting action items for meeting {meeting_id}")
    # TODO: Implement with Instructor + Pydantic schema
    return {"status": "pending", "meeting_id": meeting_id}

from enum import Enum

from pydantic import BaseModel


class IngestionStatus(str, Enum):
    OK = "ok"
    NEEDS_FALLBACK = "needs_fallback"  # readable PDF but too little text (scanned/image)
    DUPLICATE = "duplicate"
    ERROR = "error"                    # unreadable / malformed


class IngestedDocument(BaseModel):
    source_file: str
    path: str | None = None  # kept so fallback extraction can render the pages
    status: IngestionStatus
    content_hash: str | None = None
    text: str = ""
    page_count: int = 0
    duplicate_of: str | None = None
    error: str | None = None        # technical detail, for logs only
    error_code: str | None = None

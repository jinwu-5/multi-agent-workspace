from pydantic import BaseModel, Field
from typing import Optional


class AskReq(BaseModel):
    """Request model for natural language queries"""
    question: str = Field(..., description="Natural language question about the data")
    database: Optional[str] = Field(None, description="Target database name (optional)")
    max_retry_attempts: int = Field(2, ge=0, le=5, description="Maximum retry attempts for failed queries")
    as_table: bool = Field(False, description="Return result as markdown table")

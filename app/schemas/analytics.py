"""
Analytics Schemas

Pydantic models for creator analytics.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class StudentAnalyticsRow(BaseModel):
    """Schema for a single row in the student analytics table."""
    
    student_name: str = Field(..., description="Full name of the student")
    student_email: str = Field(..., description="Email of the student")
    enrolled_at: datetime = Field(..., description="Date when student enrolled")
    completion_percentage: float = Field(..., description="Percentage of videos watched")
    average_quiz_score: Optional[float] = Field(None, description="Average score across all quizzes")
    certificate_issued: bool = Field(..., description="Whether a certificate has been issued")
    
    model_config = {"from_attributes": True}

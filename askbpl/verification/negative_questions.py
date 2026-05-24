"""Out-of-corpus questions that should refuse at the retrieval gate."""

from __future__ import annotations

NEGATIVE_QUESTIONS: list[str] = [
    "What is the weather forecast for Brooklyn tomorrow?",
    "How do I configure Microsoft Azure Active Directory?",
    "What are the best practices for Kubernetes pod autoscaling?",
    "Who won the World Series last year?",
    "How do I apply for a passport?",
    "What is the HIPAA retention period for medical records at hospitals?",
]

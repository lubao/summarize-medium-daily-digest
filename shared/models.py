"""
Data models for the Medium Digest Summarizer application.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Article:
    """Data model for Medium articles."""
    url: str
    title: str
    content: str
    summary: str = ""
    author: str = ""
    
    def to_dict(self) -> Dict[str, str]:
        """Convert article to dictionary format."""
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "author": self.author
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'Article':
        """Create Article instance from dictionary."""
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            author=data.get("author", "")
        )


@dataclass
class ProcessingResult:
    """Data model for API responses and processing results."""
    success: bool
    articles_processed: int
    errors: List[str]
    execution_time: float
    
    def to_response(self) -> Dict:
        """Convert to API Gateway response format."""
        return {
            "statusCode": 200 if self.success else 500,
            "body": {
                "message": "Processing completed" if self.success else "Processing failed",
                "articlesProcessed": self.articles_processed,
                "errors": self.errors,
                "executionTime": self.execution_time
            }
        }
    
    def to_dict(self) -> Dict:
        """Convert to dictionary format."""
        return {
            "success": self.success,
            "articles_processed": self.articles_processed,
            "errors": self.errors,
            "execution_time": self.execution_time
        }
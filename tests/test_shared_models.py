"""
Unit tests for shared data models.
"""
import pytest
from shared.models import Article, ProcessingResult


class TestArticle:
    """Test cases for the Article data model."""
    
    def test_article_creation(self):
        """Test basic article creation."""
        article = Article(
            url="https://medium.com/test-article",
            title="Test Article",
            content="This is test content",
            summary="Test summary"
        )
        
        assert article.url == "https://medium.com/test-article"
        assert article.title == "Test Article"
        assert article.content == "This is test content"
        assert article.summary == "Test summary"
    
    def test_article_creation_with_defaults(self):
        """Test article creation with default summary."""
        article = Article(
            url="https://medium.com/test-article",
            title="Test Article",
            content="This is test content"
        )
        
        assert article.summary == ""
    
    def test_article_to_dict(self):
        """Test converting article to dictionary."""
        article = Article(
            url="https://medium.com/test-article",
            title="Test Article",
            content="This is test content",
            summary="Test summary"
        )
        
        expected_dict = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "content": "This is test content",
            "summary": "Test summary"
        }
        
        assert article.to_dict() == expected_dict
    
    def test_article_from_dict(self):
        """Test creating article from dictionary."""
        data = {
            "url": "https://medium.com/test-article",
            "title": "Test Article",
            "content": "This is test content",
            "summary": "Test summary"
        }
        
        article = Article.from_dict(data)
        
        assert article.url == "https://medium.com/test-article"
        assert article.title == "Test Article"
        assert article.content == "This is test content"
        assert article.summary == "Test summary"
    
    def test_article_from_dict_with_missing_fields(self):
        """Test creating article from dictionary with missing fields."""
        data = {
            "url": "https://medium.com/test-article",
            "title": "Test Article"
        }
        
        article = Article.from_dict(data)
        
        assert article.url == "https://medium.com/test-article"
        assert article.title == "Test Article"
        assert article.content == ""
        assert article.summary == ""
    
    def test_article_from_empty_dict(self):
        """Test creating article from empty dictionary."""
        article = Article.from_dict({})
        
        assert article.url == ""
        assert article.title == ""
        assert article.content == ""
        assert article.summary == ""


class TestProcessingResult:
    """Test cases for the ProcessingResult data model."""
    
    def test_processing_result_creation(self):
        """Test basic processing result creation."""
        result = ProcessingResult(
            success=True,
            articles_processed=3,
            errors=["Error 1", "Error 2"],
            execution_time=1.5
        )
        
        assert result.success is True
        assert result.articles_processed == 3
        assert result.errors == ["Error 1", "Error 2"]
        assert result.execution_time == 1.5
    
    def test_processing_result_to_response_success(self):
        """Test converting successful processing result to API response."""
        result = ProcessingResult(
            success=True,
            articles_processed=3,
            errors=[],
            execution_time=1.5
        )
        
        expected_response = {
            "statusCode": 200,
            "body": {
                "message": "Processing completed",
                "articlesProcessed": 3,
                "errors": [],
                "executionTime": 1.5
            }
        }
        
        assert result.to_response() == expected_response
    
    def test_processing_result_to_response_failure(self):
        """Test converting failed processing result to API response."""
        result = ProcessingResult(
            success=False,
            articles_processed=1,
            errors=["Network error", "Authentication failed"],
            execution_time=2.3
        )
        
        expected_response = {
            "statusCode": 500,
            "body": {
                "message": "Processing failed",
                "articlesProcessed": 1,
                "errors": ["Network error", "Authentication failed"],
                "executionTime": 2.3
            }
        }
        
        assert result.to_response() == expected_response
    
    def test_processing_result_to_dict(self):
        """Test converting processing result to dictionary."""
        result = ProcessingResult(
            success=True,
            articles_processed=2,
            errors=["Warning message"],
            execution_time=0.8
        )
        
        expected_dict = {
            "success": True,
            "articles_processed": 2,
            "errors": ["Warning message"],
            "execution_time": 0.8
        }
        
        assert result.to_dict() == expected_dict
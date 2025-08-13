"""
Integration tests for the fetch articles Lambda function.
"""
import json
import pytest
from unittest.mock import Mock, patch

# Import the module under test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from lambdas.fetch_articles import lambda_handler
from shared.models import Article


class TestFetchArticlesIntegration:
    """Integration test cases for the fetch articles Lambda function."""
    
    def create_mock_context(self):
        """Create a properly mocked Lambda context."""
        context = Mock()
        context.aws_request_id = "test-request-id"
        context.function_name = "test-function"
        context.function_version = "1"
        context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
        context.memory_limit_in_mb = "512"
        context.get_remaining_time_in_millis = Mock(return_value=30000)
        return context
    
    @patch('lambdas.fetch_articles.get_medium_cookies')
    @patch('lambdas.fetch_articles.requests.get')
    def test_end_to_end_article_fetch(self, mock_get, mock_cookies):
        """Test complete end-to-end article fetching workflow."""
        # Mock cookies in JSON array format
        mock_cookies.return_value = [
            {
                "name": "session",
                "value": "abc123",
                "domain": ".medium.com",
                "secure": True
            },
            {
                "name": "uid", 
                "value": "user123",
                "domain": ".medium.com",
                "secure": True
            },
            {
                "name": "sid",
                "value": "session456", 
                "domain": ".medium.com",
                "secure": True
            }
        ]
        
        # Mock successful HTTP response with realistic Medium HTML
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"test content"
        mock_response.headers = {'content-type': 'text/html'}
        mock_response.text = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>How to Build Better Software - Medium</title>
            <meta property="og:title" content="How to Build Better Software">
        </head>
        <body>
            <article>
                <section>
                    <h1 data-testid="storyTitle">How to Build Better Software</h1>
                    <div data-testid="storyContent">
                        <p>Building better software requires understanding your users and their needs. This comprehensive guide will walk you through the essential principles.</p>
                        <h2>Understanding User Requirements</h2>
                        <p>The first step in building better software is to truly understand what your users need. This involves conducting thorough research and gathering feedback.</p>
                        <h2>Design Principles</h2>
                        <p>Good software design follows certain principles that make the code maintainable, scalable, and robust. These principles include separation of concerns, single responsibility, and dependency inversion.</p>
                        <h2>Testing and Quality Assurance</h2>
                        <p>Testing is crucial for ensuring software quality. Implement unit tests, integration tests, and end-to-end tests to catch bugs early in the development process.</p>
                        <p>Quality assurance goes beyond testing and includes code reviews, static analysis, and continuous monitoring of production systems.</p>
                        <h2>Conclusion</h2>
                        <p>Building better software is an ongoing process that requires dedication to best practices, continuous learning, and a focus on user needs.</p>
                    </div>
                </section>
            </article>
        </body>
        </html>
        """
        mock_get.return_value = mock_response
        
        # Test event
        event = {
            "url": "https://medium.com/@author/how-to-build-better-software-123abc"
        }
        context = self.create_mock_context()
        
        # Execute the Lambda handler
        result = lambda_handler(event, context)
        
        # Verify the response
        assert result["statusCode"] == 200
        assert "body" in result
        
        body = result["body"]
        assert body["url"] == "https://medium.com/@author/how-to-build-better-software-123abc"
        assert body["title"] == "How to Build Better Software"
        assert "Building better software requires understanding" in body["content"]
        assert "Understanding User Requirements" in body["content"]
        assert "Design Principles" in body["content"]
        assert "Testing and Quality Assurance" in body["content"]
        assert "Conclusion" in body["content"]
        assert body["summary"] == ""  # Summary should be empty initially
        
        # Verify the HTTP request was made correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        
        # Check URL
        assert call_args[0][0] == "https://medium.com/@author/how-to-build-better-software-123abc"
        
        # Check cookies were passed
        assert "cookies" in call_args[1]
        expected_cookies = {"session": "abc123", "uid": "user123", "sid": "session456"}
        assert call_args[1]["cookies"] == expected_cookies
        
        # Check headers were set
        assert "headers" in call_args[1]
        headers = call_args[1]["headers"]
        assert "User-Agent" in headers
        assert "Mozilla" in headers["User-Agent"]
        assert headers["Accept"] == 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        
        # Check other request parameters
        assert call_args[1]["timeout"] == 30
        assert call_args[1]["allow_redirects"] is True
    
    @patch('lambdas.fetch_articles.get_medium_cookies')
    @patch('lambdas.fetch_articles.requests.get')
    def test_realistic_medium_article_structure(self, mock_get, mock_cookies):
        """Test with realistic Medium article HTML structure."""
        # Mock cookies in JSON array format
        mock_cookies.return_value = [
            {
                "name": "session",
                "value": "test123",
                "domain": ".medium.com",
                "secure": True
            }
        ]
        
        # Mock response with more realistic Medium HTML structure
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"test content"
        mock_response.headers = {'content-type': 'text/html'}
        mock_response.text = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>The Future of AI Development</title>
        </head>
        <body>
            <div class="meteredContent">
                <article>
                    <section>
                        <h1 class="graf--title">The Future of AI Development</h1>
                        <div class="postArticle-content">
                            <p class="graf graf--p">Artificial Intelligence is rapidly evolving, and developers need to stay ahead of the curve. This article explores the latest trends and technologies shaping the future of AI development.</p>
                            <p class="graf graf--p">Machine learning frameworks are becoming more accessible, enabling developers to build sophisticated AI applications with less complexity than ever before.</p>
                            <h3 class="graf graf--h3">Key Technologies to Watch</h3>
                            <p class="graf graf--p">Several emerging technologies are particularly important for AI developers to understand and master in the coming years.</p>
                            <blockquote class="graf graf--blockquote">The future belongs to those who can adapt and learn continuously in the rapidly changing landscape of AI technology.</blockquote>
                            <p class="graf graf--p">As we look toward the future, it's clear that AI development will continue to democratize, making powerful tools available to a broader range of developers and organizations.</p>
                        </div>
                    </section>
                </article>
            </div>
        </body>
        </html>
        """
        mock_get.return_value = mock_response
        
        # Test event
        event = {
            "url": "https://towardsdatascience.com/the-future-of-ai-development-456def"
        }
        context = self.create_mock_context()
        
        # Execute the Lambda handler
        result = lambda_handler(event, context)
        
        # Verify the response
        assert result["statusCode"] == 200
        body = result["body"]
        
        assert body["title"] == "The Future of AI Development"
        assert "Artificial Intelligence is rapidly evolving" in body["content"]
        assert "Key Technologies to Watch" in body["content"]
        assert "The future belongs to those who can adapt" in body["content"]
        assert "democratize" in body["content"]
        
        # Verify content structure
        content_lines = body["content"].split('\n\n')
        assert len(content_lines) >= 4  # Should have multiple paragraphs
    
    @patch('lambdas.fetch_articles.get_medium_cookies')
    @patch('lambdas.fetch_articles.requests.get')
    def test_error_handling_with_retry(self, mock_get, mock_cookies):
        """Test error handling and retry logic in integration scenario."""
        # Mock cookies in JSON array format
        mock_cookies.return_value = [
            {
                "name": "session",
                "value": "test123",
                "domain": ".medium.com",
                "secure": True
            }
        ]
        
        # First call returns 429 (rate limit), second call succeeds
        mock_response_fail = Mock()
        mock_response_fail.status_code = 429
        
        mock_response_success = Mock()
        mock_response_success.status_code = 200
        mock_response_success.content = b"test content"
        mock_response_success.headers = {'content-type': 'text/html'}
        mock_response_success.text = """
        <html>
            <body>
                <h1 data-testid="storyTitle">Test Article After Retry</h1>
                <article>
                    <section>
                        <p>This article was successfully fetched after a retry due to rate limiting.</p>
                        <p>The retry mechanism worked correctly and the content was extracted properly.</p>
                    </section>
                </article>
            </body>
        </html>
        """
        
        mock_get.side_effect = [mock_response_fail, mock_response_success]
        
        # Test event
        event = {
            "url": "https://medium.com/@author/test-retry-article"
        }
        context = self.create_mock_context()
        
        # Execute the Lambda handler (should succeed after retry)
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = lambda_handler(event, context)
        
        # Verify the response
        assert result["statusCode"] == 200
        body = result["body"]
        
        assert body["title"] == "Test Article After Retry"
        assert "successfully fetched after a retry" in body["content"]
        assert "retry mechanism worked correctly" in body["content"]
        
        # Verify retry occurred
        assert mock_get.call_count == 2
    
    def test_invalid_url_validation(self):
        """Test URL validation in integration scenario."""
        event = {
            "url": "https://invalid-site.com/not-medium-article"
        }
        context = self.create_mock_context()
        
        result = lambda_handler(event, context)
        
        assert result["statusCode"] == 400
        assert "Validation error" in result["body"]["error"]
        assert "Invalid Medium URL" in result["body"]["message"]
    
    def test_missing_url_parameter(self):
        """Test missing URL parameter in integration scenario."""
        event = {}  # No URL provided
        context = self.create_mock_context()
        
        result = lambda_handler(event, context)
        
        assert result["statusCode"] == 400
        assert "Validation error" in result["body"]["error"]
        assert "Missing 'url'" in result["body"]["message"]


if __name__ == "__main__":
    pytest.main([__file__])
"""
Simple unit tests for the fetch articles Lambda function focusing on JSON cookie functionality.
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


def create_mock_context():
    """Create a mock Lambda context with proper attributes."""
    context = Mock()
    context.aws_request_id = "test-request-id"
    context.function_name = "test-function"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
    context.memory_limit_in_mb = "512"
    context.get_remaining_time_in_millis = Mock(return_value=30000)
    return context


class TestFetchArticlesJsonCookies:
    """Test cases for fetch articles with JSON cookie format."""
    
    @patch('lambdas.fetch_articles.get_medium_cookies')
    @patch('lambdas.fetch_articles.requests.get')
    def test_json_cookie_format_success(self, mock_get, mock_cookies):
        """Test successful article fetching with JSON cookie format."""
        # Mock cookies in JSON array format
        mock_cookies.return_value = [
            {
                "name": "uid",
                "value": "aa1a02b88c89",
                "domain": ".medium.com",
                "secure": True,
                "httpOnly": True
            },
            {
                "name": "sid",
                "value": "1:test123",
                "domain": ".medium.com",
                "secure": True,
                "httpOnly": True
            }
        ]
        
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"test content"
        mock_response.headers = {'content-type': 'text/html'}
        mock_response.text = """
        <html>
            <body>
                <h1 data-testid="storyTitle">Test Article</h1>
                <article>
                    <section>
                        <p>This is test content for the article.</p>
                    </section>
                </article>
            </body>
        </html>
        """
        mock_get.return_value = mock_response
        
        # Test event
        event = {
            "url": "https://medium.com/@author/test-article"
        }
        context = create_mock_context()
        
        # Execute the Lambda handler
        result = lambda_handler(event, context)
        
        # Verify the response
        assert result["statusCode"] == 200
        assert "body" in result
        
        body = result["body"]
        assert body["url"] == "https://medium.com/@author/test-article"
        assert body["title"] == "Test Article"
        assert "test content" in body["content"]
        
        # Verify the HTTP request was made with correct cookies
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        
        # Check that cookies were formatted correctly for HTTP request
        assert "cookies" in call_args[1]
        cookies = call_args[1]["cookies"]
        assert cookies["uid"] == "aa1a02b88c89"
        assert cookies["sid"] == "1:test123"
    
    def test_missing_url_parameter(self):
        """Test missing URL parameter."""
        event = {}  # No URL provided
        context = create_mock_context()
        
        result = lambda_handler(event, context)
        
        assert result["statusCode"] == 400
        assert "Validation error" in result["body"]["error"]
        assert "Missing 'url'" in result["body"]["message"]
    
    def test_invalid_url_validation(self):
        """Test URL validation."""
        event = {
            "url": "https://invalid-site.com/not-medium-article"
        }
        context = create_mock_context()
        
        result = lambda_handler(event, context)
        
        assert result["statusCode"] == 400
        assert "Validation error" in result["body"]["error"]
        assert "Invalid Medium URL" in result["body"]["message"]


if __name__ == "__main__":
    pytest.main([__file__])
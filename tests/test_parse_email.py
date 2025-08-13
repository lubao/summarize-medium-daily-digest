"""
Unit tests for the Parse Email Lambda function.
"""
import json
import pytest
from unittest.mock import patch, MagicMock

# Import the functions to test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from lambdas.parse_email import (
    lambda_handler,
    extract_email_content,
    parse_email_content,
    validate_medium_urls,
    is_valid_medium_url
)
from shared.error_handling import ValidationError
from shared.logging_utils import create_lambda_logger


class TestLambdaHandler:
    """Test cases for the main lambda_handler function."""
    
    def test_successful_email_parsing(self):
        """Test successful parsing of email with Medium articles."""
        event = {
            "payload": """
            <html>
                <body>
                    <p>Here are today's articles:</p>
                    <a href="https://medium.com/@author/great-article-123abc">Great Article</a>
                    <a href="https://towardsdatascience.medium.com/data-science-article-456def">Data Science</a>
                </body>
            </html>
            """
        }
        
        result = lambda_handler(event, {})
        
        assert result["statusCode"] == 200
        assert "articles" in result["body"]
        assert len(result["body"]["articles"]) == 2
        assert result["body"]["articles"][0]["url"] == "https://medium.com/@author/great-article-123abc"
        assert result["body"]["articles"][1]["url"] == "https://towardsdatascience.medium.com/data-science-article-456def"
    
    def test_no_articles_found(self):
        """Test handling when no Medium articles are found."""
        event = {
            "payload": """
            <html>
                <body>
                    <p>No articles today!</p>
                    <a href="https://google.com">Google</a>
                </body>
            </html>
            """
        }
        
        result = lambda_handler(event, {})
        
        assert result["statusCode"] == 200
        assert result["body"]["message"] == "No valid Medium articles found"
        assert result["body"]["articles"] == []
    
    def test_missing_payload(self):
        """Test error handling for missing payload."""
        event = {}
        
        result = lambda_handler(event, {})
        
        assert result["statusCode"] == 500
        assert "error" in result["body"]
    
    def test_empty_payload(self):
        """Test error handling for empty payload."""
        event = {"payload": ""}
        
        result = lambda_handler(event, {})
        
        assert result["statusCode"] == 500
        assert "error" in result["body"]
    
    def test_malformed_html(self):
        """Test handling of malformed HTML content."""
        event = {
            "payload": "<html><body><a href='https://medium.com/@test/article-123'>Article</a></body>"
        }
        
        result = lambda_handler(event, {})
        
        # Should still work with malformed HTML due to BeautifulSoup's robustness
        assert result["statusCode"] == 200
        assert len(result["body"]["articles"]) == 1


class TestExtractEmailContent:
    """Test cases for extract_email_content function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.logger = create_lambda_logger("test", {}, {})
    
    def test_string_payload(self):
        """Test extraction from string payload."""
        event = {"payload": "This is email content"}
        result = extract_email_content(event, self.logger)
        assert result == "This is email content"
    
    def test_dict_payload_with_body(self):
        """Test extraction from dictionary payload with body key."""
        event = {
            "payload": {
                "body": "Email body content",
                "subject": "Test Subject"
            }
        }
        result = extract_email_content(event, self.logger)
        assert result == "Email body content"
    
    def test_dict_payload_with_content(self):
        """Test extraction from dictionary payload with content key."""
        event = {
            "payload": {
                "content": "Email content here",
                "from": "sender@example.com"
            }
        }
        result = extract_email_content(event, self.logger)
        assert result == "Email content here"
    
    def test_dict_payload_with_html(self):
        """Test extraction from dictionary payload with html key."""
        event = {
            "payload": {
                "html": "<html><body>HTML content</body></html>",
                "text": "Plain text"
            }
        }
        result = extract_email_content(event, self.logger)
        assert result == "<html><body>HTML content</body></html>"
    
    def test_dict_payload_fallback(self):
        """Test fallback to JSON string for dictionary payload."""
        event = {
            "payload": {
                "custom_field": "Some content",
                "another_field": "More data"
            }
        }
        result = extract_email_content(event, self.logger)
        # Should return JSON string representation
        assert "custom_field" in result
        assert "Some content" in result
    
    def test_missing_payload_key(self):
        """Test error when payload key is missing."""
        event = {"data": "some data"}
        
        with pytest.raises(ValidationError, match="Missing 'payload' key"):
            extract_email_content(event, self.logger)
    
    def test_empty_string_payload(self):
        """Test error when payload is empty string."""
        event = {"payload": ""}
        
        with pytest.raises(ValidationError, match="Email payload is empty"):
            extract_email_content(event, self.logger)
    
    def test_empty_dict_payload(self):
        """Test error when payload is empty dictionary."""
        event = {"payload": {}}
        
        with pytest.raises(ValidationError, match="Email payload is empty"):
            extract_email_content(event, self.logger)


class TestParseEmailContent:
    """Test cases for parse_email_content function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.logger = create_lambda_logger("test", {}, {})
    
    def test_parse_html_with_links(self):
        """Test parsing HTML content with Medium links."""
        html_content = """
        <html>
            <body>
                <h1>Daily Digest</h1>
                <a href="https://medium.com/@author1/article-1-abc123">Article 1</a>
                <a href="https://towardsdatascience.medium.com/article-2-def456">Article 2</a>
                <a href="https://google.com">Not Medium</a>
            </body>
        </html>
        """
        
        urls = parse_email_content(html_content, self.logger)
        
        assert len(urls) == 3  # All URLs extracted, validation happens later
        assert "https://medium.com/@author1/article-1-abc123" in urls
        assert "https://towardsdatascience.medium.com/article-2-def456" in urls
        assert "https://google.com" in urls
    
    def test_parse_plain_text_urls(self):
        """Test parsing plain text content with URLs."""
        text_content = """
        Check out these articles:
        https://medium.com/@writer/amazing-story-123
        https://uxdesign.medium.com/design-principles-456
        """
        
        urls = parse_email_content(text_content, self.logger)
        
        assert len(urls) == 2
        assert "https://medium.com/@writer/amazing-story-123" in urls
        assert "https://uxdesign.medium.com/design-principles-456" in urls
    
    def test_parse_mixed_content(self):
        """Test parsing content with both HTML links and plain text URLs."""
        mixed_content = """
        <html>
            <body>
                <a href="https://medium.com/@author/html-link-article">HTML Link</a>
                <p>Also check: https://medium.com/@author/plain-text-article</p>
            </body>
        </html>
        """
        
        urls = parse_email_content(mixed_content, self.logger)
        
        assert len(urls) == 2
        assert "https://medium.com/@author/html-link-article" in urls
        assert "https://medium.com/@author/plain-text-article" in urls
    
    def test_remove_duplicates(self):
        """Test that duplicate URLs are removed."""
        html_content = """
        <html>
            <body>
                <a href="https://medium.com/@author/article-123">Article</a>
                <a href="https://medium.com/@author/article-123">Same Article</a>
                <p>Link again: https://medium.com/@author/article-123</p>
            </body>
        </html>
        """
        
        urls = parse_email_content(html_content, self.logger)
        
        assert len(urls) == 1
        assert urls[0] == "https://medium.com/@author/article-123"
    
    def test_empty_content(self):
        """Test parsing empty content."""
        urls = parse_email_content("", self.logger)
        assert urls == []
    
    def test_no_links_found(self):
        """Test parsing content with no links."""
        html_content = "<html><body><p>No links here!</p></body></html>"
        urls = parse_email_content(html_content, self.logger)
        assert urls == []


class TestValidateMediumUrls:
    """Test cases for validate_medium_urls function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.logger = create_lambda_logger("test", {}, {})
    
    def test_filter_valid_medium_urls(self):
        """Test filtering to keep only valid Medium URLs."""
        urls = [
            "https://medium.com/@author/article-123",
            "https://towardsdatascience.medium.com/data-article-456",
            "https://google.com/search",
            "https://medium.com/publication/story-789",
            "http://medium.com/insecure-article",  # HTTP not HTTPS
            "https://fake-medium.com/article"
        ]
        
        valid_urls = validate_medium_urls(urls, self.logger)
        
        assert len(valid_urls) == 3
        assert "https://medium.com/@author/article-123" in valid_urls
        assert "https://towardsdatascience.medium.com/data-article-456" in valid_urls
        assert "https://medium.com/publication/story-789" in valid_urls
    
    def test_empty_url_list(self):
        """Test validation with empty URL list."""
        valid_urls = validate_medium_urls([], self.logger)
        assert valid_urls == []


class TestIsValidMediumUrl:
    """Test cases for is_valid_medium_url function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.logger = create_lambda_logger("test", {}, {})
    
    def test_valid_medium_com_urls(self):
        """Test validation of valid medium.com URLs."""
        valid_urls = [
            "https://medium.com/@author/article-title-123abc",
            "https://medium.com/publication/story-title-456def",
            "https://www.medium.com/@writer/post-789ghi"
        ]
        
        for url in valid_urls:
            assert is_valid_medium_url(url, self.logger), f"Should be valid: {url}"
    
    def test_valid_subdomain_medium_urls(self):
        """Test validation of valid subdomain.medium.com URLs."""
        valid_urls = [
            "https://towardsdatascience.medium.com/article-123",
            "https://uxdesign.medium.com/design-post-456",
            "https://levelup.medium.com/coding-tutorial-789"
        ]
        
        for url in valid_urls:
            assert is_valid_medium_url(url, self.logger), f"Should be valid: {url}"
    
    def test_invalid_non_medium_urls(self):
        """Test rejection of non-Medium URLs."""
        invalid_urls = [
            "https://google.com/search",
            "https://github.com/user/repo",
            "https://stackoverflow.com/questions/123",
            "https://fake-medium.com/article",
            "https://medium-fake.com/story"
        ]
        
        for url in invalid_urls:
            assert not is_valid_medium_url(url, self.logger), f"Should be invalid: {url}"
    
    def test_invalid_http_urls(self):
        """Test rejection of HTTP (non-HTTPS) URLs."""
        invalid_urls = [
            "http://medium.com/@author/article",
            "http://towardsdatascience.medium.com/post"
        ]
        
        for url in invalid_urls:
            assert not is_valid_medium_url(url, self.logger), f"Should be invalid (HTTP): {url}"
    
    def test_invalid_malformed_urls(self):
        """Test rejection of malformed URLs."""
        invalid_urls = [
            "not-a-url",
            "https://",
            "medium.com/article",  # Missing protocol
            "https://medium.com",  # No path
            "https://medium.com/",  # Root path only
        ]
        
        for url in invalid_urls:
            assert not is_valid_medium_url(url, self.logger), f"Should be invalid (malformed): {url}"
    
    def test_invalid_excluded_paths(self):
        """Test rejection of excluded Medium paths."""
        invalid_urls = [
            "https://medium.com/about",
            "https://medium.com/privacy",
            "https://medium.com/terms",
            "https://medium.com/help",
            "https://medium.com/membership",
            "https://medium.com/settings"
        ]
        
        for url in invalid_urls:
            assert not is_valid_medium_url(url, self.logger), f"Should be invalid (excluded path): {url}"
    
    def test_invalid_non_article_patterns(self):
        """Test rejection of URLs that don't match article patterns."""
        invalid_urls = [
            "https://medium.com/search?q=test",
            "https://medium.com/tag/technology",
            "https://medium.com/topics/programming"
        ]
        
        for url in invalid_urls:
            assert not is_valid_medium_url(url, self.logger), f"Should be invalid (non-article pattern): {url}"
    
    def test_edge_cases(self):
        """Test edge cases for URL validation."""
        # Test with query parameters (should still be valid)
        assert is_valid_medium_url("https://medium.com/@author/article-123?source=rss", self.logger)
        
        # Test with fragments (should still be valid)
        assert is_valid_medium_url("https://medium.com/@author/article-123#section1", self.logger)
        
        # Test with both query and fragment
        assert is_valid_medium_url("https://medium.com/@author/article-123?source=rss#intro", self.logger)


if __name__ == "__main__":
    pytest.main([__file__])
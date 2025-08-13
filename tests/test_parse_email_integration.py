"""
Integration tests for the Parse Email Lambda function with realistic email content.
"""
import json
import pytest

# Import the functions to test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from lambdas.parse_email import lambda_handler


class TestParseEmailIntegration:
    """Integration test cases with realistic Medium Daily Digest email content."""
    
    def test_realistic_medium_digest_email(self):
        """Test with a realistic Medium Daily Digest email structure."""
        # This simulates the structure of an actual Medium Daily Digest email
        realistic_email_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Medium Daily Digest</title>
        </head>
        <body>
            <div class="digest-container">
                <h1>Your Daily Digest</h1>
                <p>Here are today's top stories from Medium:</p>
                
                <div class="article-section">
                    <h2>Technology</h2>
                    <div class="article-item">
                        <a href="https://medium.com/@techwriter/the-future-of-ai-development-2024-abc123def" 
                           style="text-decoration: none;">
                            <h3>The Future of AI Development in 2024</h3>
                        </a>
                        <p>Exploring the latest trends in artificial intelligence...</p>
                    </div>
                    
                    <div class="article-item">
                        <a href="https://towardsdatascience.medium.com/machine-learning-best-practices-456ghi789">
                            <h3>Machine Learning Best Practices</h3>
                        </a>
                        <p>A comprehensive guide to ML engineering...</p>
                    </div>
                </div>
                
                <div class="article-section">
                    <h2>Design</h2>
                    <div class="article-item">
                        <a href="https://uxdesign.medium.com/user-experience-trends-2024-jkl012mno">
                            <h3>UX Design Trends for 2024</h3>
                        </a>
                        <p>What's next in user experience design...</p>
                    </div>
                </div>
                
                <div class="footer">
                    <p>You're receiving this because you subscribed to Medium Daily Digest.</p>
                    <a href="https://medium.com/unsubscribe">Unsubscribe</a> |
                    <a href="https://medium.com/help">Help</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        event = {"payload": realistic_email_html}
        
        result = lambda_handler(event, {})
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert "articles" in result["body"]
        
        articles = result["body"]["articles"]
        assert len(articles) == 3  # Should find 3 valid Medium articles
        
        # Verify the extracted URLs
        expected_urls = [
            "https://medium.com/@techwriter/the-future-of-ai-development-2024-abc123def",
            "https://towardsdatascience.medium.com/machine-learning-best-practices-456ghi789",
            "https://uxdesign.medium.com/user-experience-trends-2024-jkl012mno"
        ]
        
        extracted_urls = [article["url"] for article in articles]
        
        for expected_url in expected_urls:
            assert expected_url in extracted_urls, f"Expected URL not found: {expected_url}"
        
        # Verify article structure
        for article in articles:
            assert "url" in article
            assert "title" in article
            assert "content" in article
            assert "summary" in article
            assert article["title"] == ""  # Should be empty initially
            assert article["content"] == ""  # Should be empty initially
            assert article["summary"] == ""  # Should be empty initially
    
    def test_email_with_mixed_valid_invalid_links(self):
        """Test email containing both valid Medium links and other links."""
        mixed_email_html = """
        <html>
        <body>
            <h1>Daily Reading List</h1>
            
            <!-- Valid Medium articles -->
            <a href="https://medium.com/@author1/great-article-123">Great Article</a>
            <a href="https://levelup.medium.com/coding-tips-456">Coding Tips</a>
            
            <!-- Invalid/non-Medium links that should be filtered out -->
            <a href="https://google.com/search?q=medium">Google Search</a>
            <a href="https://github.com/user/repo">GitHub Repo</a>
            <a href="https://medium.com/about">Medium About Page</a>
            <a href="http://medium.com/insecure-article">HTTP Article</a>
            
            <!-- Another valid Medium article -->
            <a href="https://medium.com/publication/another-story-789">Another Story</a>
            
            <!-- Plain text URL that should be extracted -->
            Check out: https://betterhumans.medium.com/self-improvement-guide-abc
        </body>
        </html>
        """
        
        event = {"payload": mixed_email_html}
        
        result = lambda_handler(event, {})
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert "articles" in result["body"]
        
        articles = result["body"]["articles"]
        assert len(articles) == 4  # Should find 4 valid Medium articles
        
        # Verify only valid Medium URLs are included
        extracted_urls = [article["url"] for article in articles]
        
        # These should be included
        valid_urls = [
            "https://medium.com/@author1/great-article-123",
            "https://levelup.medium.com/coding-tips-456",
            "https://medium.com/publication/another-story-789",
            "https://betterhumans.medium.com/self-improvement-guide-abc"
        ]
        
        for valid_url in valid_urls:
            assert valid_url in extracted_urls, f"Valid URL should be included: {valid_url}"
        
        # These should be excluded
        invalid_urls = [
            "https://google.com/search?q=medium",
            "https://github.com/user/repo",
            "https://medium.com/about",
            "http://medium.com/insecure-article"
        ]
        
        for invalid_url in invalid_urls:
            assert invalid_url not in extracted_urls, f"Invalid URL should be excluded: {invalid_url}"
    
    def test_email_with_api_gateway_payload_structure(self):
        """Test with payload structure that might come from API Gateway."""
        # Simulate API Gateway event structure
        api_gateway_event = {
            "payload": {
                "body": """
                <html>
                <body>
                    <h1>Medium Digest</h1>
                    <a href="https://medium.com/@writer/story-123">Story 1</a>
                    <a href="https://uxdesign.medium.com/design-story-456">Story 2</a>
                </body>
                </html>
                """,
                "headers": {
                    "Content-Type": "text/html"
                }
            }
        }
        
        result = lambda_handler(api_gateway_event, {})
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert "articles" in result["body"]
        
        articles = result["body"]["articles"]
        assert len(articles) == 2
        
        expected_urls = [
            "https://medium.com/@writer/story-123",
            "https://uxdesign.medium.com/design-story-456"
        ]
        
        extracted_urls = [article["url"] for article in articles]
        
        for expected_url in expected_urls:
            assert expected_url in extracted_urls
    
    def test_email_with_no_medium_articles(self):
        """Test email that contains no Medium articles."""
        no_medium_email = """
        <html>
        <body>
            <h1>Daily Newsletter</h1>
            <p>Today's links:</p>
            <a href="https://news.ycombinator.com">Hacker News</a>
            <a href="https://stackoverflow.com/questions/123">Stack Overflow</a>
            <a href="https://github.com/trending">GitHub Trending</a>
        </body>
        </html>
        """
        
        event = {"payload": no_medium_email}
        
        result = lambda_handler(event, {})
        
        # Should still return success but with no articles
        assert result["statusCode"] == 200
        assert result["body"]["message"] == "No valid Medium articles found"
        assert result["body"]["articles"] == []
    
    def test_email_with_duplicate_articles(self):
        """Test email containing duplicate Medium article links."""
        duplicate_email = """
        <html>
        <body>
            <h1>Featured Articles</h1>
            
            <!-- Same article linked multiple times -->
            <a href="https://medium.com/@author/popular-article-123">Popular Article</a>
            <p>Also mentioned: https://medium.com/@author/popular-article-123</p>
            <a href="https://medium.com/@author/popular-article-123">Popular Article (Again)</a>
            
            <!-- Different article -->
            <a href="https://towardsdatascience.medium.com/data-analysis-456">Data Analysis</a>
        </body>
        </html>
        """
        
        event = {"payload": duplicate_email}
        
        result = lambda_handler(event, {})
        
        # Verify successful processing
        assert result["statusCode"] == 200
        assert "articles" in result["body"]
        
        articles = result["body"]["articles"]
        assert len(articles) == 2  # Should deduplicate to 2 unique articles
        
        extracted_urls = [article["url"] for article in articles]
        
        # Should contain both unique URLs
        assert "https://medium.com/@author/popular-article-123" in extracted_urls
        assert "https://towardsdatascience.medium.com/data-analysis-456" in extracted_urls
        
        # Verify no duplicates
        assert len(extracted_urls) == len(set(extracted_urls))


if __name__ == "__main__":
    pytest.main([__file__])
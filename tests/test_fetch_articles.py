"""
Unit tests for the fetch articles Lambda function.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import requests
from requests.exceptions import Timeout, ConnectionError, RequestException

# Import the module under test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from lambdas.fetch_articles import (
    lambda_handler,
    is_valid_medium_url,
    fetch_article_content,
    parse_cookies_string,
    extract_article_data,
    extract_article_title,
    extract_article_content,
    clean_text,
    MediumFetchError
)
from shared.models import Article
from shared.secrets_manager import SecretsManagerError
from shared.error_handling import (
    AuthenticationError,
    ValidationError,
    RateLimitError,
    NetworkError
)


def create_mock_context():
    """Create a mock Lambda context with proper attributes."""
    class MockContext:
        def __init__(self):
            self.aws_request_id = "test-request-id"
            self.function_name = "test-function"
            self.memory_limit_in_mb = 256
            self.function_version = "$LATEST"
            self.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test-function"
            self.log_group_name = "/aws/lambda/test-function"
            self.log_stream_name = "2023/01/01/[$LATEST]abcdef123456"
        
        def remaining_time_in_millis(self):
            return 30000
    
    return MockContext()


class TestLambdaHandler:
    """Test cases for the main lambda handler."""
    
    def test_lambda_handler_success(self):
        """Test successful article fetching."""
        event = {
            "url": "https://medium.com/@author/test-article-123"
        }
        context = create_mock_context()
        
        mock_article = Article(
            url="https://medium.com/@author/test-article-123",
            title="Test Article",
            content="This is test content."
        )
        
        with patch('lambdas.fetch_articles.fetch_article_content', return_value=mock_article):
            result = lambda_handler(event, context)
        
        assert result["statusCode"] == 200
        assert result["body"]["url"] == "https://medium.com/@author/test-article-123"
        assert result["body"]["title"] == "Test Article"
        assert result["body"]["content"] == "This is test content."
    
    def test_lambda_handler_missing_url(self):
        """Test handler with missing URL."""
        event = {}
    context()
        
        result = lambda_handler(event, context)
        
        assert result["s== 400
        assert "Validation error" in result["body""]
        assert "Missing 'url'" in result["body""]
    
    def test_lambda_handler_invalid_url(self):
        ""
        event = {
        
        }
        context = create_mock_context()
        
    
        
        assert result["statusCode"] == 400
        assert "V
        assert "Invalid Medium URL" in result["body"]e"]
    
    def test_lambda_handf):
        """Test handler with authentication error.
        event = {
            "url": "https://medium.com/@e-123"
        }
        ()
        
        , 
                  side_effect=Authenticati
            result = lambda_handler(event, context)
        
    
        assert "Authentication error" in result["body"]
    
    def test_lamb
        """Test handler with Medium fetch error."""
        e{
            "url": "http
        }
        context = create_mock_context()
        
        with patch('lambdas.fetch_articles.fetch_article', 
        )):
            result = lambda_handler(event, context)
        
        assert result["statusCode"] == 500
        "error"]
    
    def test_lambda_handler_unexpected_error(self):
    "
        event = {
            "url": "https://medium.com/@author/test
        }
        context = create_mock_context()
        
        with patch('lamb
                  side_effect=Exception("Unexpecte):
            with patch('lambdas.fetch_articles. 
                      return_value={"sta
                result = lambda_handler(event, context)
        
        assert result["statusCode"] == 500
        mock_handle.assert_called_once()


class TestUrlValidation:
    """Test cases for URL validation."""
    
    def test_valid_medium_urls(self):
        """Test various valid Medium URLs."""
        from sharr
        
        vrls = [
            "https://med
            "https://towardsdatascience.com/articl",
            "https://hackernoon.com/article-tit",
            "https://uxdesign.cc/article
            "https://levelup.gitconnected.com/article-ti
        ",
            "https://medium.com/publication/article-title-jkl"
        ]
        
        context = create_mock_context()
        logger = create_lambda_logger("test", {}, conte
        
        for url in valid_urls:
            assert is_valid_medium_url(u"
    

        """Test various ""
        from shared.logging_utils importger
      
        invalid_urls = [
            "https://google.com/search",
            "https://facebook.com/post",
        ",
            "https://m
            "not-a-url",
            "",
            "ftp://medium.com/article",
            "https://medium.co.uk/article"  # Wrong TLD
        ]
        
        context = create_mock_context()
        l
        
        for url in invalid_urls:
            assert not is_valid_medium_url(url, logger)
    
    def test_malformed_urls(self):
        """Test malformed URLs."""
        r
        
        s = [
            "http://",
            "https://",
    ticle",
            "://medium.com/article"
        ]
        
        xt()
        logger = create_)
        
        for url in malformed_urls:
            assert not is_valid_me {url}"


class TestFetchntent:
    """Test cases for article content f"
    
    @patc
    @patget')
    def test_fetch_article_co):
        """Test successful article content fetching."""
        from shared.logging_utils import create_lamb
        
        # Mock cookies
        
        
        
        mock_response = Mock()
        mock_response.status_code = 200
    l'}
        mock_response.content = b"
        mock_response.text = """
        <html>
        d>
            <body>
                <h1 da1>
                <articl>
                    <section>
                        <p>This is /p>
         .</p>
        ion>
                </article>
            </body>
        </html>
        """
        mock_get.return_value = mock_response
        
        context = create_mock_context()
        text)
        tracker = PerformanceTrack
        

tracker)
        
        assert isinstance(result, Article)
    
        assert result.title == "Test Article Title"
        assert "first paragraph" in result.content
        assert "second paragraph" in result.content
        
        # Verify request was made with correct parameters
        once()
        call_args = moall_args
        assert call_args[0][0] == url
        ll_args[1]
        assert 'headers' in call_args[1]
        assert call_args[1]['t 30
    
    @patch('lambdas.fetch_articles.get_medium_cookies')
    def test_fetch_article_content_secrets_erros):
        """Test fetch with Secre."""
        from ser
        
        mock_cooki")
        
        context = create_)
        logger = create_lambdxt)
        tracker = PerformanceTracker()
        
        url = "https://medium.cle"
        
        with pytestnfo:
            feter)
        
        assert "Failed to retrieve Medium coo
    
    @patch('lambdas.fetch_artkies')
    @patch('lambdas.fetch_articles.requests.get')
    def test_fetch_article_content_rate_limit(self, 
        """Test fetch with rate limiting."""
        from shared.logging_utils import create_lambda_logger
        
        mock_cookies.return_value = "session=abc123"
        
        
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        context = create_mock_context()
        logger = create_lambda_lcontext)
        tracker = PerformanceTracker()
        
        url = "https://medium.com/@author/test-arti"
        
        with pytest.raises(RateLimitError) as exc_info:
            fetch_article_content(urlker)
        
        assert "Rate limited by Mediu
    
    @patch('lambdas.fetch_articles.get_m
    @patch('lambdas.fetch_articles.requests.t')
    
        """Test fetch with authentication error."""
        from shared.logging_utils import create_lambda_logger, Perforracker
        
        mock_cookies.return_value = "session=abc123"
        
        mock_response = Mock()
        401
        mock_get.return_valueonse
        
        context = create_mock_context()
        logger = create_lambda_logger("test",ntext)
        tracker = PerformanceTracker()
        
        url = "https://medium.com/@author/test-article"
        
        fo:
            fetch_article_content(url, logger, tracker)
        
        assert "Authentication failed" in str(exc_info.value)
    
    @patkies')
    @patch('lambdas.fetch_articles.requests.get')
    
        """Test fetch with server error."""
        from shared.logging_utils import create_l
        
        mock_cookies.return_value = "session"
        
        Mock()
        mock_response.status_code = 500
        
        
        context = create_mock_context()
        logger = create_lambda_logger("test",
        
        
        url = "https://medium.com/@author/test-article"
        
        with pytest.raises(NetworkError) as einfo:
            fetch_article_content(url, logger, tracker)
        
        assert "Server error" in str(exc_info.value)
    
    @paties')
    @patch('lambdas.fetch_articles.requests.get')
    def 
        """Test fetch with timeout error."""
        from shared.logging_utils import create_lambda_nceTracker
        
        mock_cookies.return_value = "session=abc123"
    meout")
        
        context = create_mock_context()
        logger = create_lambda_logger("test", {}, context)
        tracker = PerformanceTracker()
        
        e"
        
        c_info:
            fetch_article_contker)
        
        assert "Request timeout" in str(exc_ilue)
    
    @patch('lambdas.fetch_art
    @patch('lambdas.fetch_articles.requests.get')
    def test_fetch_article_content_connection_error(
        """Test fetch with connection error."
        from shared.logging_utils import create_lambda_logger
        
        mock_cookies.return_value = "session=abc123"
        mock_get.side_effect = Connect failed")
        
        context = create_mock_context()
        ontext)
        tracker = PerformanceTracker()
        
        icle"
        
    
            fetch_article_content(url, logger, tracker)
        
        assert "Connection error" in str(exc_info.value)


class Teing:
    """Test cases for cookie string parsing."""
    
    def test_parse_cookies_str
        """Test parsing valid cookie st
        from shared.logging_utils import crea
        
        context = create_mock
        logger = create_lambda_logger("test", {}, conte
        
        cookies_string = "session=abc123; usek"
        result = parse_cookies_string(cookies_string, logger)
        
        expected = {
            "session": "abc123",
        
            "theme": "dark"
        }
        assert result == expected
    
    def elf):
        """Test parsing cookie string with extra spas."""
    r
        
        context = create_mock_context()
        logger = create_lambda_logger("test", {}, context)
        
        cookies_string = " session = abc123 ; user = testuser ; theme = dark "
        , logger)
        
        expected = {
        ,
            "user": "testuser",
            "theme": "dark"
        }
        assert result == expected
    
    def 
        """Test parsing empty cookie string."""
        from shared.logging_utils impo
        
        context = create_mock_context()
        xt)
        
        result = parse_cookies_string("", logger)
        == {}
        
    )
        assert result == {}
    
    def test_parse_cookies_string_single_cookie(self):
        """Test parsing single cookie."""
        from shared.logging_utils import create_lambda_logger
        
        context = create_mock_context()
        logger = create_lambda_logger("test", {}, context)
        
        cookies_string = "ses123"
        result = parse_cookies_string(cookies_string, lr)
        
        expected = {"session": "abc123"}
        assert result == expected
    
    def test_parse_cookies_string_malformed(self):
        """Test parsing malformed cook""
        
        
        ()
        logger = create_lambda_logger("test", {}, con)
        
        
        result = parse_cookies_string(cookies_string, lo
 
nes
        expected = {
            "session": "abc123",
    
        }
        assert result == expected


class TestHtmlParsing:
    """Test cases for HTML content extraction."""
    
    def test_extract_article_data_success(sel
        """Test successful article data extraction."""
        er
        
        
        logger = create_lambda_logger("test", {}, context)
        
        ""
        <html>
            <head><title>Test Ar
            <body>
                <h1 data-te>
         cle>
                    <section>
    p>
                        <p>This is the second paragr
                        <h2>Subheading</h2>
                        <p>Content under the subheading with ls.</p>
        on>
                </article>
            </body>
        </html>
        """
        
        article"
        result = extract_article_data(html_content, url, logger)
        
        assert result["title"] == "Test Article Title"
        assert "first paragraph" in result["content"]
        
        assert "Subh"]
        assert "additional detai"]
    
    def test_extract_articl(self):
        "
        from shared.logging_utils
     
        context = create_mock_context()
        logger = create_lambda_logger("test", {)
        
        
        <html>
            <body>
                <article>
                    <section>
                        <p>Content without title.</p>
        on>
                </article>
        >
        </html>
        """
        
        url = "https://medium.com/@author/test-arti
        
    
            extract_article_data(html_content, url, lo
        
        assert "Could not extract title" in str(exc_info.valu)
    
    def test_extract_article_lf):
        """Test extraction with missing content."""
        from shared.logging_utils import create_lambda_logger
        
        context = create_mock_context()
        ntext)
        
        
        <html>
            <body>
        >
                <div>No article content 
            </body>
    /html>
        """
        
        url = "https://medium.com/@author/test-article"
        
        with pytest.raises(Me
            extract_article_data(html_content, url, logger)
        
        assert "Could not extract content" ine)
    
    def f):
        """Test title extraction from various HTML formats."""
        up
        
        # Test new Medium format
        >'
        soup1 = BeautifulSoup(html1, 'html.parser')
        assert extra"
        
        # Test classic Medium 
        hh1>'
        soup2 = BeautifulSoup(htmser')
 Title"

        # Test microformat
        html3 = '<h1 class="p-name">Microformat T</h1>'
    )
        assert extract_article_title(soup3) == ""
        
        # Test generic h1
        
        soup4 = BeautifulSoup')
        assert extract_article_title(soup4) == "Generic"
    
    def test_extract_article_content_various_f):
        """Test content extraction from various HTML formats.""
        ifulSoup
        
        ormat
        html1 = '''
        <artic>
            <section>
                <pp>
                <p>Second paragraph with more information.</p>
            </section>
        </article>
        '''
        soup1 = BeautifulSoup(html1, 'html.parser')
        content1 = extract_article_content(
        assert "First paragraph content" in content1
        assert "Second paragra
        
        # Test new 
        html2 = '''
        <di
        p>
            <p>Story content paragraph two.</p>
        </div>
        
        soup2 = BeautifulSoup(html2, 'html.parser')
        content2 = extract_article_content(soup2)
        assert "Story content paragraph one" in content2
        assert "Story content paragraph two" in ntent2


class TestTextCleaning:
    """Test cases for text cleaning functionality
    
    def 
        """Test cleaning extr""
        text = "  This   has    extra   whitespace  "
        result = clean_text(text)
        assert result == "This has extra white"
    
    def f):
        """Test removing Medium-specific artifacts."""
        llow"
        result1 = clean_teext1)
        assertt"
        
        text2 = "InterestSign up"
        result2 = clean_text(
        assert result2 == "Interesting post"
        
        text3 = "Good read
        result3 = cext3)
        assert  read"
    
    def y(self):
        """Test cleaning empty or None text."""
        
        assert clean_text(None) == ""
        assert clean_text("   ") == ""
    
    def test_clean_text_newlines(self):
    "
        text = "Line one\n\n\nLine two\n   Line three"
        result = clean_text(text)
        assert result == "Line one Line two Line three"


class TestRetryLogic:
    """Test cases for retry logic and error handling
    
    @patch('lambdas.fetch_articles.get_medium_cookies')
    @pat
    def test_retry_on_rate_limit(self, mock_get, mock_cookies):
        """
        from shared.loggin
        
        mock_cooki"
        
        # First call returns 429, second call succeds
        mock_respon= Mock()
        mock_re
        
        ock()
        mock_response_success.status_code = 200
        ml'}
        mock_response_success.content = b"test content"
        mock_response_success.text = """
        <html>
            <h1 data-testid="storyTitle">Test Title</h1>
    cle>
        </html>
        """
        
        _success]
        
        context = create_mock_context()
        logger = create_lambda_logger("test", {}, c
        tracker = PerformanceTracker()
        
        url = "https://medium.com/@a
        
        # Should succeed after retry
        with patch('time.sleep'):  # Mock sleep to speed up test
        acker)
        
        assert isinstance(result, Article)
        assert result.title == "Test Title"
        assert mock_get.call_count == 2
    
    @patch('lambdas.fetchkies')
    @patch('lambdas.fetch_articles.requet')
    def test_no_retry_on_auth_error(self, mock_get,s):
        """Test that authentication errors are not retried."""
    
        
        mock_cookies.return_value = "session=abc123"
        
        ck()
        mock_response.status_code = 401
        mock_get.re
        
        context = cre_context()
        logger = create_lambda_logger("test", {}, coext)
        tracker = PerformanceTracker()
        
        url = "htt"
        
        with pytest.raises(AuthenticationError):
            fetch_article_content(url, logger, trker)
        
        # Should only be called once (no retry)
        1


if __name__ == "__main__":
    pytest.main([__file__])
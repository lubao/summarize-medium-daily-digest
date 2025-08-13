"""
Lambda function for fetching individual article content from Medium.
"""
import json
import re
from typing import Dict, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.models import Article
from shared.secrets_manager import get_medium_cookies, SecretsManagerError
from shared.error_handling import (
    medium_api_retry,
    RateLimitError,
    NetworkError,
    AuthenticationError,
    ValidationError,
    handle_fatal_error,
    send_admin_notification
)
from shared.logging_utils import (
    create_lambda_logger, StructuredLogger, ErrorCategory, PerformanceTracker
)


class MediumFetchError(Exception):
    """Custom exception for Medium article fetching errors."""
    pass


def lambda_handler(event: Dict, context) -> Dict:
    """
    Lambda handler for fetching individual article content from Medium.
    
    Args:
        event: Lambda event containing article URL
        context: Lambda context object
        
    Returns:
        Dictionary containing article data or error information
    """
    # Initialize structured logger and performance tracker
    logger = create_lambda_logger("fetch_articles", event, context)
    tracker = PerformanceTracker()
    
    try:
        logger.log_execution_start("fetch_articles_lambda", event_keys=list(event.keys()))
        
        # Extract article URL from event
        article_url = event.get('url')
        if not article_url:
            logger.error("Missing 'url' in event payload", 
                        event_structure=list(event.keys()),
                        category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Missing 'url' in event payload")
        
        logger.info("Extracted article URL from event", url=article_url)
        
        # Validate URL format
        tracker.checkpoint("url_validation_start")
        if not is_valid_medium_url(article_url, logger):
            logger.error("Invalid Medium URL provided", 
                        url=article_url,
                        category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError(f"Invalid Medium URL: {article_url}")
        tracker.checkpoint("url_validation_complete")
        
        logger.info("URL validation passed", url=article_url)
        
        # Fetch article content
        tracker.checkpoint("fetch_content_start")
        article = fetch_article_content(article_url, logger, tracker)
        tracker.checkpoint("fetch_content_complete")
        
        # Record success metrics
        metrics = tracker.get_metrics()
        metrics.update({
            "article_title_length": len(article.title),
            "article_content_length": len(article.content),
            "fetch_success": True
        })
        
        logger.log_execution_end("fetch_articles_lambda", success=True, metrics=metrics)
        
        return {
            "statusCode": 200,
            "body": article.to_dict()
        }
        
    except ValidationError as e:
        logger.error("Validation error occurred", error=e, 
                    category=ErrorCategory.INPUT_VALIDATION,
                    url=event.get('url'),
                    metrics=tracker.get_metrics())
        return {
            "statusCode": 400,
            "body": {
                "error": "Validation error",
                "message": str(e)
            }
        }
        
    except AuthenticationError as e:
        logger.critical("Authentication error occurred", error=e, 
                       category=ErrorCategory.AUTHENTICATION,
                       url=event.get('url'),
                       metrics=tracker.get_metrics())
        return {
            "statusCode": 401,
            "body": {
                "error": "Authentication error",
                "message": "Failed to authenticate with Medium"
            }
        }
        
    except MediumFetchError as e:
        logger.error("Medium fetch error occurred", error=e, 
                    category=ErrorCategory.EXTERNAL_SERVICE,
                    url=event.get('url'),
                    metrics=tracker.get_metrics())
        return {
            "statusCode": 500,
            "body": {
                "error": "Fetch error",
                "message": str(e)
            }
        }
        
    except Exception as e:
        logger.critical("Unexpected error in fetch_articles_lambda", error=e, 
                       category=ErrorCategory.UNKNOWN,
                       url=event.get('url'),
                       metrics=tracker.get_metrics())
        return handle_fatal_error(e, "fetch_articles_lambda")


def is_valid_medium_url(url: str, logger: StructuredLogger) -> bool:
    """
    Validate that the URL is a valid Medium article URL.
    
    Args:
        url: URL to validate
        logger: Structured logger instance
        
    Returns:
        True if valid Medium URL, False otherwise
    """
    try:
        parsed = urlparse(url)
        
        # Check if it's HTTPS protocol
        if parsed.scheme != 'https':
            logger.debug("Invalid URL scheme", url=url, scheme=parsed.scheme)
            return False
        
        # Check if it's a Medium domain
        valid_domains = [
            'medium.com',
            'towardsdatascience.com',
            'hackernoon.com',
            'uxdesign.cc',
            'levelup.gitconnected.com'
        ]
        
        # Check for medium.com or custom Medium domains
        is_medium_domain = (
            parsed.netloc == 'medium.com' or
            parsed.netloc.endswith('.medium.com') or
            parsed.netloc in valid_domains
        )
        
        if not is_medium_domain:
            logger.debug("Invalid domain", url=url, domain=parsed.netloc)
            return False
        
        # Check for valid path structure
        has_valid_path = len(parsed.path) > 1 and parsed.path != '/'
        
        if not has_valid_path:
            logger.debug("Invalid path structure", url=url, path=parsed.path)
            return False
        
        logger.debug("URL validation passed", url=url, domain=parsed.netloc)
        return True
        
    except Exception as e:
        logger.debug("URL validation error", url=url, error=e)
        return False


@medium_api_retry
def fetch_article_content(url: str, logger: StructuredLogger, tracker: PerformanceTracker) -> Article:
    """
    Fetch article content from Medium using stored cookies.
    
    Args:
        url: Medium article URL
        logger: Structured logger instance
        tracker: Performance tracker instance
        
    Returns:
        Article object with fetched content
        
    Raises:
        AuthenticationError: If authentication with Medium fails
        RateLimitError: If rate limited by Medium
        NetworkError: If network request fails
        MediumFetchError: If article content cannot be extracted
    """
    try:
        logger.info("Starting article content fetch", url=url)
        
        # Get Medium cookies from Secrets Manager
        tracker.checkpoint("get_cookies_start")
        cookies_list = get_medium_cookies()
        tracker.checkpoint("get_cookies_complete")
        
        logger.info("Retrieved Medium cookies from Secrets Manager", 
                   cookie_count=len(cookies_list) if cookies_list else 0)
        
        # Convert cookie objects to dictionary format for requests
        from shared.secrets_manager import format_cookies_for_requests
        cookies = format_cookies_for_requests(cookies_list)
        logger.info("Formatted cookies for HTTP requests", cookie_count=len(cookies))
        
        # Set up headers to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        logger.info("Making HTTP request to Medium", url=url, timeout=30)
        
        # Add a small delay to be respectful to Medium's servers
        import time
        time.sleep(1)  # 1 second delay between requests
        
        # Make HTTP request with cookies and headers
        tracker.checkpoint("http_request_start")
        response = requests.get(
            url,
            cookies=cookies,
            headers=headers,
            timeout=30,
            allow_redirects=True
        )
        tracker.checkpoint("http_request_complete")
        tracker.record_metric("response_status_code", response.status_code)
        tracker.record_metric("response_size_bytes", len(response.content))
        
        logger.info("Received HTTP response", 
                   status_code=response.status_code,
                   response_size=len(response.content),
                   content_type=response.headers.get('content-type'))
        
        # Handle different response status codes
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', '60')
            logger.warning("Rate limited by Medium", 
                          status_code=response.status_code,
                          url=url,
                          retry_after=retry_after,
                          category=ErrorCategory.RATE_LIMIT)
            raise RateLimitError(f"Rate limited by Medium (429): {url}. Retry after {retry_after} seconds")
        elif response.status_code == 401 or response.status_code == 403:
            logger.error("Authentication failed with Medium", 
                        status_code=response.status_code,
                        url=url,
                        category=ErrorCategory.AUTHENTICATION)
            raise AuthenticationError(f"Authentication failed (status {response.status_code}): {url}")
        elif response.status_code >= 500:
            logger.error("Medium server error", 
                        status_code=response.status_code,
                        url=url,
                        category=ErrorCategory.EXTERNAL_SERVICE)
            raise NetworkError(f"Server error (status {response.status_code}): {url}")
        elif response.status_code != 200:
            logger.error("HTTP error from Medium", 
                        status_code=response.status_code,
                        url=url,
                        category=ErrorCategory.EXTERNAL_SERVICE)
            raise NetworkError(f"HTTP error (status {response.status_code}): {url}")
        
        # Extract article data from HTML
        tracker.checkpoint("extract_data_start")
        article_data = extract_article_data(response.text, url, logger)
        tracker.checkpoint("extract_data_complete")
        
        logger.info("Successfully extracted article data", 
                   title=article_data['title'][:100] + "..." if len(article_data['title']) > 100 else article_data['title'],
                   content_length=len(article_data['content']))
        
        return Article(
            url=url,
            title=article_data['title'],
            content=article_data['content']
        )
        
    except (RateLimitError, AuthenticationError, NetworkError):
        # Re-raise these specific errors without wrapping
        raise
    except SecretsManagerError as e:
        logger.error_with_notification("Failed to retrieve Medium cookies", error=e, 
                    category=ErrorCategory.AUTHENTICATION,
                    severity="ERROR",
                    url=url)
        raise AuthenticationError(f"Failed to retrieve Medium cookies: {str(e)}")
    except requests.exceptions.Timeout:
        logger.error("Request timeout", url=url, timeout=30,
                    category=ErrorCategory.NETWORK)
        raise NetworkError(f"Request timeout for URL: {url}")
    except requests.exceptions.ConnectionError as e:
        logger.error("Connection error", url=url, error=e,
                    category=ErrorCategory.NETWORK)
        raise NetworkError(f"Connection error for URL: {url}")
    except requests.exceptions.RequestException as e:
        logger.error("Request exception", url=url, error=e,
                    category=ErrorCategory.NETWORK)
        raise NetworkError(f"Request failed for URL {url}: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error fetching article", url=url, error=e,
                    category=ErrorCategory.PROCESSING)
        raise MediumFetchError(f"Failed to fetch article content: {str(e)}")





def extract_article_data(html_content: str, url: str, logger: StructuredLogger) -> Dict[str, str]:
    """
    Extract article title and main content from HTML.
    
    Args:
        html_content: Raw HTML content from Medium
        url: Article URL for context
        
    Returns:
        Dictionary containing 'title' and 'content' keys
        
    Raises:
        MediumFetchError: If article data cannot be extracted
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract title
        title = extract_article_title(soup)
        if not title:
            raise MediumFetchError(f"Could not extract title from article: {url}")
        
        # Extract main content
        content = extract_article_content(soup)
        if not content:
            raise MediumFetchError(f"Could not extract content from article: {url}")
        
        logger.info(f"Extracted article data - Title: {title[:50]}..., Content length: {len(content)}")
        
        return {
            'title': title,
            'content': content
        }
        
    except Exception as e:
        raise MediumFetchError(f"Failed to parse HTML content: {str(e)}")


def extract_article_title(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract article title from BeautifulSoup object.
    
    Args:
        soup: BeautifulSoup object of the HTML content
        
    Returns:
        Article title or None if not found
    """
    # Try multiple selectors for title extraction
    title_selectors = [
        'h1[data-testid="storyTitle"]',  # New Medium format
        'h1.graf--title',                # Classic Medium format
        'h1.p-name',                     # Microformat
        'h1',                            # Generic h1
        'title',                         # HTML title tag
        '[data-testid="storyTitle"]',    # Alternative data attribute
        '.graf--h3.graf--leading',       # Some Medium articles use h3
    ]
    
    for selector in title_selectors:
        title_element = soup.select_one(selector)
        if title_element:
            title = title_element.get_text(strip=True)
            if title and len(title) > 5:  # Ensure it's a meaningful title
                return clean_text(title)
    
    return None


def extract_article_content(soup: BeautifulSoup) -> Optional[str]:
    """
    Extract main article content from BeautifulSoup object.
    
    Args:
        soup: BeautifulSoup object of the HTML content
        
    Returns:
        Article content or None if not found
    """
    # Remove unwanted elements
    for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside']):
        element.decompose()
    
    # Try multiple selectors for content extraction
    content_selectors = [
        'article section',               # Main article section
        '[data-testid="storyContent"]',  # New Medium format
        '.postArticle-content',          # Classic Medium format
        '.e-content',                    # Microformat
        'article',                       # Generic article tag
        '.section-content',              # Alternative format
        '.story-content',                # Another format
    ]
    
    for selector in content_selectors:
        content_container = soup.select_one(selector)
        if content_container:
            # Extract text from paragraphs and headings
            content_elements = content_container.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'li'])
            
            if content_elements:
                content_parts = []
                for element in content_elements:
                    text = element.get_text(strip=True)
                    if text and len(text) > 5:  # Filter out very short text
                        content_parts.append(clean_text(text))
                
                if content_parts:
                    content = '\n\n'.join(content_parts)
                    if len(content) > 100:  # Ensure meaningful content length
                        return content
    
    # Fallback: extract all paragraph text
    paragraphs = soup.find_all('p')
    if paragraphs:
        content_parts = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text and len(text) > 20:  # Filter out short paragraphs
                content_parts.append(clean_text(text))
        
        if content_parts:
            return '\n\n'.join(content_parts)
    
    return None


def clean_text(text: str) -> str:
    """
    Clean and normalize text content.
    
    Args:
        text: Raw text to clean
        
    Returns:
        Cleaned text
    """
    if not text:
        return ""
    
    # Remove extra whitespace and normalize
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Remove common Medium artifacts
    text = re.sub(r'Follow\s*$', '', text)
    text = re.sub(r'Sign up\s*$', '', text)
    text = re.sub(r'Sign in\s*$', '', text)
    
    return text.strip()
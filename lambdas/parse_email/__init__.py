"""
Parse Email Lambda function for extracting Medium article links from Daily Digest emails.
"""
import json
import re
from typing import Dict, List, Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.error_handling import ValidationError, handle_fatal_error
from shared.models import Article
from shared.logging_utils import (
    create_lambda_logger, StructuredLogger, ErrorCategory, PerformanceTracker
)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for parsing Medium Daily Digest email content.
    
    Args:
        event: Lambda event containing the email payload
        context: Lambda context object
        
    Returns:
        Dictionary containing extracted article URLs or error response
    """
    # Initialize structured logger and performance tracker
    logger = create_lambda_logger("parse_email", event, context)
    tracker = PerformanceTracker()
    
    try:
        logger.log_execution_start("parse_email_lambda", event_keys=list(event.keys()))
        
        # Extract email content from payload
        tracker.checkpoint("extract_content_start")
        email_content = extract_email_content(event, logger)
        tracker.checkpoint("extract_content_complete")
        tracker.record_metric("email_content_size_chars", len(email_content))
        
        logger.info("Successfully extracted email content", 
                   content_size=len(email_content))
        
        # Parse email content to extract articles with titles and authors
        tracker.checkpoint("parse_content_start")
        articles = parse_email_content(email_content, logger)
        tracker.checkpoint("parse_content_complete")
        tracker.record_metric("articles_found", len(articles))
        
        logger.info("Extracted articles from email content", 
                   articles_count=len(articles))
        
        if not articles:
            logger.warning("No Medium articles found in email content")
            
            # Log success metrics even for empty results
            metrics = tracker.get_metrics()
            logger.log_success_metrics(metrics, result="no_articles_found")
            
            return []
        
        # Convert Article objects to dictionaries for JSON response
        article_dicts = [article.to_dict() for article in articles]
        
        # Log success metrics
        metrics = tracker.get_metrics()
        metrics.update({
            "articles_extracted": len(articles),
            "success": True
        })
        
        logger.log_execution_end("parse_email_lambda", success=True, metrics=metrics)
        
        return article_dicts
        
    except ValidationError as e:
        logger.error("Validation error occurred", error=e, 
                    category=ErrorCategory.INPUT_VALIDATION,
                    metrics=tracker.get_metrics())
        return handle_fatal_error(e, "parse_email_lambda")
    
    except Exception as e:
        logger.critical("Unexpected error in parse_email_lambda", error=e, 
                       category=ErrorCategory.UNKNOWN,
                       metrics=tracker.get_metrics(),
                       event_keys=list(event.keys()) if isinstance(event, dict) else None)
        return handle_fatal_error(e, "parse_email_lambda")


def extract_email_content(event: Dict[str, Any], logger: StructuredLogger) -> str:
    """
    Extract email content from the Lambda event payload.
    
    Args:
        event: Lambda event dictionary
        logger: Structured logger instance
        
    Returns:
        Email content as string
        
    Raises:
        ValidationError: If payload is missing or invalid
    """
    try:
        logger.info("Starting email content extraction", event_structure=list(event.keys()))
        
        # Check if payload key exists
        if "payload" not in event:
            logger.error("Missing 'payload' key in request", 
                        available_keys=list(event.keys()),
                        category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Missing 'payload' key in request")
        
        payload = event["payload"]
        logger.info("Found payload in event", payload_type=type(payload).__name__)
        
        # Handle case where payload is already a string
        if isinstance(payload, str):
            if not payload.strip():
                logger.error("Email payload is empty string")
                raise ValidationError("Email payload is empty")
            logger.info("Payload is string format", payload_size=len(payload))
            return payload
        
        # Handle case where payload is a dictionary (from API Gateway)
        if isinstance(payload, dict):
            logger.info("Payload is dictionary format", payload_keys=list(payload.keys()))
            
            # Look for common email content keys
            content_keys = ["body", "content", "html", "message"]
            for key in content_keys:
                if key in payload and payload[key]:
                    content = str(payload[key])
                    logger.info(f"Found email content in '{key}' field", content_size=len(content))
                    return content
            
            # If no content found, convert entire payload to string
            if payload:
                content = json.dumps(payload)
                logger.info("Converted entire payload to JSON string", content_size=len(content))
                return content
            else:
                logger.error("Email payload dictionary is empty")
                raise ValidationError("Email payload is empty")
        
        # Convert other types to string
        email_content = str(payload)
        if not email_content.strip():
            logger.error("Email payload is empty after string conversion", 
                        original_type=type(payload).__name__)
            raise ValidationError("Email payload is empty")
        
        logger.info("Converted payload to string", 
                   original_type=type(payload).__name__, 
                   content_size=len(email_content))
        return email_content
        
    except ValidationError:
        raise
    except (TypeError, json.JSONDecodeError) as e:
        logger.error("Invalid payload format", error=e, 
                    category=ErrorCategory.INPUT_VALIDATION,
                    payload_type=type(event.get("payload")).__name__)
        raise ValidationError(f"Invalid payload format: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error extracting email content", error=e,
                    category=ErrorCategory.PROCESSING)
        raise ValidationError(f"Failed to extract email content: {str(e)}")


def parse_email_content(email_html: str, logger: StructuredLogger) -> List[Article]:
    """
    Parse email HTML content to extract Medium articles with titles and authors.
    
    Args:
        email_html: HTML content of the email
        logger: Structured logger instance
        
    Returns:
        List of Article objects with URL, title, and author information
        
    Raises:
        ValidationError: If email content is malformed
    """
    try:
        logger.info("Starting email content parsing", content_size=len(email_html))
        
        # First, extract and decode the HTML content from the email
        html_content = extract_and_decode_html_content(email_html, logger)
        
        # Parse HTML content with BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        logger.info("Successfully parsed HTML with BeautifulSoup")
        
        # First, try to extract from "Today's highlights" section
        articles = extract_todays_highlights(soup, logger)
        
        # Also extract from "From your following" section if present
        following_articles = extract_from_following_section(soup, logger)
        articles.extend(following_articles)
        
        # If no articles found with specific sections, fall back to general extraction
        if not articles:
            logger.info("No articles found in specific sections, trying general extraction")
            articles = extract_articles_general(soup, logger)
        
        # Remove duplicates based on URL
        unique_articles = []
        seen_urls = set()
        for article in articles:
            if article.url not in seen_urls:
                unique_articles.append(article)
                seen_urls.add(article.url)
        
        logger.info("Successfully extracted unique articles", 
                   total_articles=len(unique_articles))
        
        return unique_articles
        
    except Exception as e:
        logger.error("Failed to parse email content", error=e, 
                    category=ErrorCategory.PROCESSING,
                    content_preview=email_html[:200] if email_html else "")
        raise ValidationError(f"Failed to parse email content: {str(e)}")


def extract_and_decode_html_content(email_content: str, logger: StructuredLogger) -> str:
    """
    Extract HTML content from email and decode it properly.
    
    Args:
        email_content: Raw email content
        logger: Structured logger instance
        
    Returns:
        Decoded HTML content
    """
    try:
        import email
        import quopri
        
        # Parse the email message
        msg = email.message_from_string(email_content)
        logger.info("Parsed email message", is_multipart=msg.is_multipart())
        
        html_content = ""
        
        if msg.is_multipart():
            # Handle multipart messages
            for part in msg.walk():
                content_type = part.get_content_type()
                logger.debug("Processing email part", content_type=content_type)
                
                if content_type == "text/html":
                    payload = part.get_payload()
                    encoding = part.get('Content-Transfer-Encoding', '').lower()
                    
                    logger.info("Found HTML content", 
                               encoding=encoding,
                               payload_size=len(payload) if payload else 0)
                    
                    if payload:
                        # Decode based on transfer encoding
                        if encoding == 'quoted-printable':
                            # Decode quoted-printable encoding
                            html_content = quopri.decodestring(payload).decode('utf-8', errors='ignore')
                            logger.info("Decoded quoted-printable content", 
                                       decoded_size=len(html_content))
                        elif encoding == 'base64':
                            import base64
                            html_content = base64.b64decode(payload).decode('utf-8', errors='ignore')
                            logger.info("Decoded base64 content", 
                                       decoded_size=len(html_content))
                        else:
                            # No special encoding or plain text
                            html_content = payload
                            logger.info("Using plain content", 
                                       content_size=len(html_content))
                        break
        else:
            # Handle single part messages
            if msg.get_content_type() == "text/html":
                payload = msg.get_payload()
                encoding = msg.get('Content-Transfer-Encoding', '').lower()
                
                if payload:
                    if encoding == 'quoted-printable':
                        html_content = quopri.decodestring(payload).decode('utf-8', errors='ignore')
                    elif encoding == 'base64':
                        import base64
                        html_content = base64.b64decode(payload).decode('utf-8', errors='ignore')
                    else:
                        html_content = payload
        
        # If no HTML content found, try to extract from the raw content
        if not html_content:
            logger.info("No HTML part found, looking for HTML in raw content")
            # Look for HTML content markers
            html_start = email_content.find('<html')
            if html_start != -1:
                html_content = email_content[html_start:]
                # Try to decode quoted-printable if it looks encoded
                if '=3D' in html_content or '=E2=' in html_content:
                    try:
                        html_content = quopri.decodestring(html_content).decode('utf-8', errors='ignore')
                        logger.info("Decoded quoted-printable from raw content")
                    except:
                        logger.warning("Failed to decode quoted-printable, using raw content")
        
        logger.info("Extracted HTML content", final_size=len(html_content))
        return html_content
        
    except Exception as e:
        logger.error("Error extracting HTML content", error=e)
        # Fallback to original content
        return email_content


def extract_todays_highlights(soup, logger: StructuredLogger) -> List[Article]:
    """
    Extract articles from the "Today's highlights" section of Medium Daily Digest.
    """
    articles = []
    try:
        # Look for "Today's highlights" text (case insensitive)
        highlights_text = soup.find(text=re.compile(r"today'?s\s+highlights?", re.IGNORECASE))
        if not highlights_text:
            logger.info("Today's highlights section not found")
            return articles
        
        logger.info("Found Today's highlights section")
        
        # Find the parent container of the highlights section
        highlights_parent = highlights_text.parent
        while highlights_parent and highlights_parent.name not in ['div', 'section', 'article', 'table', 'td']:
            highlights_parent = highlights_parent.parent
        
        if not highlights_parent:
            logger.warning("Could not find highlights parent container")
            return articles
        
        # Find the container that holds all the highlight articles
        article_container = highlights_parent.parent
        if article_container:
            # Find all article links within this container
            article_divs = article_container.find_all(['div', 'td', 'tr'], recursive=True)
            for div in article_divs:
                # Look for article title links
                title_links = div.find_all('a', href=True)
                for link in title_links:
                    href = link.get('href', '')
                    # Check if this is a Medium article URL
                    if is_valid_medium_article_url(href):
                        # Extract title from the link or nearby elements
                        title = extract_title_from_digest_link(link, div)
                        # Extract author information
                        author = extract_author_from_digest_div(div)
                        # Clean the URL
                        clean_url = clean_medium_url(href)
                        
                        if clean_url and title and len(title) > 10:
                            article = Article(
                                url=clean_url,
                                title=title,
                                author=author or "Unknown Author",
                                content="",  # Will be fetched later
                                summary=""   # Will be generated later
                            )
                            articles.append(article)
                            logger.debug("Extracted highlight article", 
                                       url=clean_url, 
                                       title=title, 
                                       author=author)
        
        logger.info("Extracted articles from Today's highlights", count=len(articles))
    except Exception as e:
        logger.error("Error extracting Today's highlights", error=e)
    
    return articles


def extract_from_following_section(soup, logger: StructuredLogger) -> List[Article]:
    """
    Extract articles from the "From your following" section.
    """
    articles = []
    try:
        # Look for "From your following" text
        following_text = soup.find(text=re.compile(r"from\s+your\s+following", re.IGNORECASE))
        if not following_text:
            logger.info("From your following section not found")
            return articles
        
        logger.info("Found From your following section")
        
        # Similar extraction logic as highlights
        following_parent = following_text.parent
        while following_parent and following_parent.name not in ['div', 'section', 'article', 'table', 'td']:
            following_parent = following_parent.parent
        
        if following_parent:
            article_container = following_parent.parent
            if article_container:
                article_divs = article_container.find_all(['div', 'td', 'tr'], recursive=True)
                for div in article_divs:
                    title_links = div.find_all('a', href=True)
                    for link in title_links:
                        href = link.get('href', '')
                        if is_valid_medium_article_url(href):
                            title = extract_title_from_digest_link(link, div)
                            author = extract_author_from_digest_div(div)
                            clean_url = clean_medium_url(href)
                            
                            if clean_url and title and len(title) > 10:
                                article = Article(
                                    url=clean_url,
                                    title=title,
                                    author=author or "Unknown Author",
                                    content="",
                                    summary=""
                                )
                                articles.append(article)
                                logger.debug("Extracted following article", 
                                           url=clean_url, 
                                           title=title, 
                                           author=author)
        
        logger.info("Extracted articles from Following section", count=len(articles))
    except Exception as e:
        logger.error("Error extracting From your following section", error=e)
    
    return articles


def extract_articles_general(soup, logger: StructuredLogger) -> List[Article]:
    """
    General article extraction as fallback method.
    """
    articles = []
    try:
        # Find all links that appear to be Medium articles
        article_links = soup.find_all('a', href=True)
        logger.info("Found potential article links", total_links=len(article_links))
        
        processed_urls = set()
        for link in article_links:
            href = link.get('href', '')
            if is_valid_medium_article_url(href):
                clean_url = clean_medium_url(href)
                if clean_url and clean_url not in processed_urls:
                    title = extract_title_from_link(link)
                    author = extract_author_from_link(link)
                    
                    if title and len(title) > 10:  # Only add if we found a meaningful title
                        article = Article(
                            url=clean_url,
                            title=title,
                            author=author or "Unknown Author",
                            content="",
                            summary=""
                        )
                        articles.append(article)
                        processed_urls.add(clean_url)
                        logger.debug("Extracted general article", 
                                   url=clean_url, 
                                   title=title, 
                                   author=author)
        
        logger.info("Extracted articles using general method", articles_count=len(articles))
    except Exception as e:
        logger.error("Error in general article extraction", error=e)
    
    return articles


def extract_title_from_digest_link(link, container_div) -> str:
    """
    Extract article title from Medium digest link structure.
    """
    # Try to get title from the link text itself
    title = link.get_text(strip=True)
    # If link text is meaningful (not just "Read more" etc.), use it
    if title and len(title) > 15 and not re.match(r'^(read\s+more|continue\s+reading|view\s+story|medium\.com)$', title, re.IGNORECASE):
        return title
    
    # Look for nearby text elements that might contain the title
    parent = link.parent
    if parent:
        # Look for text in the same cell or div
        parent_text = parent.get_text(strip=True)
        # Try to extract title from parent text (often the title is near the link)
        lines = parent_text.split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) > 15 and line != title and not re.match(r'^(by\s+|@|read\s+more)', line, re.IGNORECASE):
                return line
    
    # Look for h1, h2, h3 elements in the container
    for tag in ['h1', 'h2', 'h3']:
        header = container_div.find(tag)
        if header:
            header_text = header.get_text(strip=True)
            if header_text and len(header_text) > 10:
                return header_text
    
    return ""


def extract_author_from_digest_div(container_div) -> str:
    """
    Extract author information from Medium digest div structure.
    """
    # Look for author links (usually contain @username or author name)
    author_links = container_div.find_all('a', href=True)
    for link in author_links:
        href = link.get('href', '')
        link_text = link.get_text(strip=True)
        # Check if this is an author profile link
        if '@' in href or 'medium.com/@' in href:
            if link_text and not is_valid_medium_article_url(href):
                return link_text
    
    # Look for text patterns that indicate author names
    div_text = container_div.get_text()
    # Try to find "by Author Name" patterns
    author_match = re.search(r'by\s+([^,\n\|]+)', div_text, re.IGNORECASE)
    if author_match:
        author_name = author_match.group(1).strip()
        # Clean up common suffixes
        author_name = re.sub(r'\s+in\s+.*$', '', author_name, flags=re.IGNORECASE)
        if len(author_name) > 2 and len(author_name) < 50:
            return author_name
    
    # Try to find @username patterns
    username_match = re.search(r'@([\w\-\.]+)', div_text)
    if username_match:
        return username_match.group(1)
    
    return ""


def extract_title_from_link(link) -> str:
    """
    Extract title from a general link element.
    """
    title = link.get_text(strip=True)
    if title and len(title) > 15 and not re.match(r'^(read\s+more|continue\s+reading|view\s+story|medium\.com)$', title, re.IGNORECASE):
        return title
    return ""


def extract_author_from_link(link) -> str:
    """
    Extract author from a general link element.
    """
    # Look for author information in nearby elements
    parent = link.parent
    if parent:
        parent_text = parent.get_text()
        # Try to find "by Author Name" patterns
        author_match = re.search(r'by\s+([^,\n\|]+)', parent_text, re.IGNORECASE)
        if author_match:
            author_name = author_match.group(1).strip()
            if len(author_name) > 2 and len(author_name) < 50:
                return author_name
    return ""


def is_valid_medium_article_url(url: str) -> bool:
    """
    Check if URL is a valid Medium article URL.
    """
    if not url:
        return False
    
    # Skip non-article URLs
    skip_patterns = [
        r'help\.medium\.com',           # Help center
        r'miro\.medium\.com',           # Image CDN
        r'cdn-images-\d+\.medium\.com', # Image CDN
        r'medium\.com/plans',           # Membership plans
        r'medium\.com/me/',             # User settings
        r'medium\.com/jobs',            # Jobs page
        r'policy\.medium\.com',         # Policy pages
        r'medium\.com/\?source=',       # Homepage with tracking
        r'medium\.com/$',               # Homepage
        r'itunes\.apple\.com',          # App store
        r'play\.google\.com',           # Google Play
        r'\.css$',                      # CSS files
        r'\.js$',                       # JavaScript files
        r'\.png$|\.jpg$|\.jpeg$|\.gif$', # Image files
    ]
    
    for skip_pattern in skip_patterns:
        if re.search(skip_pattern, url, re.IGNORECASE):
            return False
    
    # Check for Medium domains and article-like patterns
    medium_patterns = [
        r'medium\.com/@[\w\-\.]+/[\w\-]+-[a-f0-9]+',  # medium.com/@author/article-hash
        r'[\w\-]+\.medium\.com/[\w\-]+-[a-f0-9]+',    # publication.medium.com/article-hash
        r'medium\.com/[\w\-]+/[\w\-]+-[a-f0-9]+',     # medium.com/publication/article-hash
        r'medium\.com/@[\w\-\.]+/[\w\-]+',            # medium.com/@author/article (without hash)
        r'[\w\-]+\.medium\.com/[\w\-]+',              # publication.medium.com/article
        r'medium\.com/[\w\-]+/[\w\-]+',               # medium.com/publication/article
    ]
    
    for pattern in medium_patterns:
        if re.search(pattern, url, re.IGNORECASE):
            return True
    
    return False


def clean_medium_url(url: str) -> str:
    """
    Clean and normalize Medium URL by removing tracking parameters.
    """
    if not url:
        return ""
    
    try:
        from urllib.parse import urlparse, parse_qs, urlunparse
        
        # Parse URL to remove tracking parameters
        parsed = urlparse(url)
        
        # Remove common tracking parameters
        query_params = parse_qs(parsed.query)
        clean_params = {}
        
        # Keep only essential parameters, remove tracking ones
        tracking_params = {'source', 'utm_source', 'utm_medium', 'utm_campaign', 
                          'utm_content', 'utm_term', 'ref', 'referrer'}
        
        for key, value in query_params.items():
            if key.lower() not in tracking_params:
                clean_params[key] = value
        
        # Reconstruct URL without tracking parameters
        clean_query = '&'.join([f"{k}={'&'.join(v)}" for k, v in clean_params.items()])
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean_query:
            clean_url += f"?{clean_query}"
        
        return clean_url
    except Exception:
        # If URL parsing fails, return original URL
        return url



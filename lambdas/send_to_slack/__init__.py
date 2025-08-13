"""
Send to Slack Lambda function for the Medium Digest Summarizer.

This function sends formatted article summaries to a Slack channel via webhook.
"""
import json
from typing import Dict, Any

import requests

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.models import Article
from shared.secrets_manager import get_slack_webhook_url, SecretsManagerError
from shared.error_handling import (
    slack_webhook_retry,
    NetworkError,
    ValidationError,
    handle_fatal_error,
    send_admin_notification
)
from shared.logging_utils import (
    create_lambda_logger, StructuredLogger, ErrorCategory, PerformanceTracker
)


def format_slack_message(title: str, summary: str, url: str) -> str:
    """
    Format article data into Slack message using specified Markdown format.
    
    Args:
        title: Article title
        summary: Article summary
        url: Article URL
        
    Returns:
        Formatted Slack message string
        
    Raises:
        ValidationError: If required fields are missing or empty
    """
    # Validate required fields
    if not title or not title.strip():
        raise ValidationError("Article title is required and cannot be empty")
    
    if not summary or not summary.strip():
        raise ValidationError("Article summary is required and cannot be empty")
    
    if not url or not url.strip():
        raise ValidationError("Article URL is required and cannot be empty")
    
    # Clean up the inputs
    title = title.strip()
    summary = summary.strip()
    url = url.strip()
    
    # Format message using the specified template
    message = f"📌 *{title}*\n\n📝 {summary}\n\n🔗 link：{url}"
    
    return message


@slack_webhook_retry
def send_webhook_request(webhook_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send HTTP request to Slack webhook with retry logic.
    
    Args:
        webhook_url: Slack webhook URL
        payload: JSON payload to send
        
    Returns:
        Response data from Slack
        
    Raises:
        NetworkError: If webhook request fails
        ValidationError: If webhook URL is invalid
    """
    try:
        # Validate webhook URL
        if not webhook_url.startswith("https://hooks.slack.com/"):
            raise ValidationError(f"Invalid Slack webhook URL: {webhook_url}")
        
        # Send POST request to Slack webhook
        response = requests.post(
            webhook_url,
            json=payload,
            headers={
                'Content-Type': 'application/json'
            },
            timeout=30
        )
        
        # Check response status
        if response.status_code == 200:
            return {"success": True, "status_code": response.status_code}
        elif response.status_code == 429:
            # Rate limited - this should trigger retry
            raise NetworkError(f"Slack webhook rate limited: {response.status_code}")
        elif response.status_code >= 500:
            # Server error - this should trigger retry
            raise NetworkError(f"Slack webhook server error: {response.status_code}")
        else:
            # Client error - this should not trigger retry
            error_msg = f"Slack webhook failed with status {response.status_code}: {response.text}"
            raise ValidationError(error_msg)
            
    except requests.exceptions.Timeout:
        raise NetworkError("Slack webhook request timed out")
    except requests.exceptions.ConnectionError:
        raise NetworkError("Failed to connect to Slack webhook")
    except requests.exceptions.RequestException as e:
        raise NetworkError(f"Slack webhook request failed: {str(e)}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for sending article summaries to Slack.
    
    Args:
        event: Lambda event containing article data
        context: Lambda context object
        
    Returns:
        Dictionary containing processing result
    """
    # Initialize structured logger and performance tracker
    logger = create_lambda_logger("send_to_slack", event, context)
    tracker = PerformanceTracker()
    
    try:
        logger.log_execution_start("send_to_slack_lambda", event_keys=list(event.keys()))
        
        # Extract article data from event
        if isinstance(event, dict) and 'article' in event:
            # Article wrapped in 'article' key
            article_data = event['article']
            logger.info("Found article data in 'article' key")
        elif isinstance(event, dict):
            # Direct article data
            article_data = event
            logger.info("Using event as direct article data")
        else:
            logger.error("Invalid event format", 
                        event_type=type(event).__name__,
                        category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Invalid event format: event must be a dictionary")
        
        # Create Article object for validation
        tracker.checkpoint("create_article_start")
        article = Article.from_dict(article_data)
        tracker.checkpoint("create_article_complete")
        
        logger.info("Created Article object", 
                   title=article.title[:50] + "..." if len(article.title) > 50 else article.title,
                   has_summary=bool(article.summary),
                   url=article.url)
        
        # Validate that we have all required fields
        if not article.title:
            logger.error("Missing article title", category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Article title is required")
        if not article.summary:
            logger.error("Missing article summary", category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Article summary is required")
        if not article.url:
            logger.error("Missing article URL", category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Article URL is required")
        
        # Get Slack webhook URL from Secrets Manager
        tracker.checkpoint("get_webhook_start")
        try:
            webhook_url = get_slack_webhook_url()
            logger.info("Retrieved Slack webhook URL from Secrets Manager")
        except SecretsManagerError as e:
            logger.critical("Failed to retrieve Slack webhook URL", error=e, 
                           category=ErrorCategory.AUTHENTICATION,
                           article_title=article.title[:50] if article.title else "Unknown")
            return handle_fatal_error(e, "Slack webhook URL retrieval")
        tracker.checkpoint("get_webhook_complete")
        
        # Format the Slack message
        tracker.checkpoint("format_message_start")
        try:
            formatted_message = format_slack_message(
                article.title,
                article.summary,
                article.url
            )
            logger.info("Formatted Slack message", message_length=len(formatted_message))
        except ValidationError as e:
            logger.error("Failed to format Slack message", error=e, 
                        category=ErrorCategory.PROCESSING)
            return handle_fatal_error(e, "Message formatting")
        tracker.checkpoint("format_message_complete")
        
        # Prepare webhook payload
        webhook_payload = {
            "summary": formatted_message
        }
        
        tracker.record_metric("payload_size", len(json.dumps(webhook_payload)))
        
        # Send message to Slack
        try:
            result = send_webhook_request(webhook_url, webhook_payload)
            
            logger.info(f"Successfully sent article to Slack: {article.title}")
            
            return {
                "statusCode": 200,
                "body": {
                    "message": "Article sent to Slack successfully",
                    "article_title": article.title,
                    "article_url": article.url,
                    "success": True
                }
            }
            
        except (NetworkError, ValidationError) as e:
            logger.error_with_notification(
                f"Failed to send message to Slack: {str(e)}",
                error=e,
                category=ErrorCategory.EXTERNAL_SERVICE if isinstance(e, NetworkError) else ErrorCategory.INPUT_VALIDATION,
                severity="ERROR",
                article_title=article.title,
                article_url=article.url
            )
            return handle_fatal_error(e, "Slack webhook")
        
    except ValidationError as e:
        logger.error(f"Validation error in Send to Slack Lambda: {str(e)}")
        return handle_fatal_error(e, "Input validation")
    
    except Exception as e:
        logger.critical(f"Unexpected error in Send to Slack Lambda: {str(e)}",
                       error=e,
                       category=ErrorCategory.UNKNOWN,
                       metrics=tracker.get_metrics())
        return handle_fatal_error(e, "Send to Slack Lambda")
"""
Lambda function for generating article summaries using AWS Bedrock Nova.
"""
import json
import logging
import os
from typing import Dict, Any

import boto3
from botocore.exceptions import ClientError

# Import shared utilities
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.models import Article
from shared.error_handling import bedrock_api_retry, RetryableError, FatalError, ValidationError
from shared.logging_utils import (
    create_lambda_logger, StructuredLogger, ErrorCategory, PerformanceTracker
)

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize Bedrock client
bedrock_client = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))

# Model configuration
MODEL_ID = "amazon.nova-pro-v1:0"
MAX_TOKENS = 500
TEMPERATURE = 0.3


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for generating article summaries using AWS Bedrock Nova.
    
    Args:
        event: Lambda event containing article data
        context: Lambda context object
        
    Returns:
        Dictionary containing the article with generated summary
    """
    # Initialize structured logger and performance tracker
    structured_logger = create_lambda_logger("summarize", event, context)
    tracker = PerformanceTracker()
    
    try:
        # Validate input first before logging
        if not isinstance(event, dict):
            structured_logger.error("Invalid input type", 
                        input_type=type(event).__name__,
                        category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Invalid input: expected dictionary")
        
        structured_logger.log_execution_start("summarize_lambda", event_keys=list(event.keys()))
        
        # Extract article data from event
        article_data = event
        
        structured_logger.info("Validated input data", article_keys=list(article_data.keys()))
        
        # Create Article object
        tracker.checkpoint("create_article_start")
        article = Article.from_dict(article_data)
        tracker.checkpoint("create_article_complete")
        
        tracker.record_metric("article_title_length", len(article.title))
        tracker.record_metric("article_content_length", len(article.content))
        
        structured_logger.info("Created Article object", 
                   title=article.title[:100] + "..." if len(article.title) > 100 else article.title,
                   content_length=len(article.content),
                   url=article.url)
        
        # Validate required fields
        if not article.title or not article.content:
            structured_logger.error("Missing required article fields", 
                        has_title=bool(article.title),
                        has_content=bool(article.content),
                        category=ErrorCategory.INPUT_VALIDATION)
            raise ValidationError("Article title and content are required")
        
        # Generate summary
        tracker.checkpoint("generate_summary_start")
        summary = generate_summary(article.content, article.title, structured_logger, tracker)
        tracker.checkpoint("generate_summary_complete")
        
        tracker.record_metric("summary_length", len(summary))
        
        # Update article with summary
        article.summary = summary
        
        # Log success metrics
        metrics = tracker.get_metrics()
        metrics.update({
            "summarization_success": True,
            "article_url": article.url
        })
        
        structured_logger.log_execution_end("summarize_lambda", success=True, metrics=metrics)
        
        # Return article data without content to reduce payload size
        return {
            "statusCode": 200,
            "body": {
                "url": article.url,
                "title": article.title,
                "author": article.author,
                "summary": article.summary
            }
        }
        
    except ValidationError as e:
        structured_logger.error("Validation error occurred", error=e, 
                    category=ErrorCategory.INPUT_VALIDATION,
                    metrics=tracker.get_metrics())
        raise e
    except Exception as e:
        structured_logger.critical("Unexpected error in summarize lambda", error=e, 
                       category=ErrorCategory.UNKNOWN,
                       metrics=tracker.get_metrics(),
                       article_url=event.get('url') if isinstance(event, dict) else None)
        raise e


@bedrock_api_retry
def generate_summary(content: str, title: str, logger: StructuredLogger, 
                    tracker: PerformanceTracker) -> str:
    """
    Generate article summary using AWS Bedrock Nova.
    
    Args:
        content: Article content to summarize
        title: Article title for context
        logger: Structured logger instance
        tracker: Performance tracker instance
        
    Returns:
        Generated summary text
        
    Raises:
        RetryableError: For retryable API failures
        FatalError: For non-retryable failures
    """
    try:
        # Format prompt for summarization
        prompt = format_prompt(content, title)
        
        # Prepare request payload
        request_payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": prompt
                        }
                    ]
                }
            ],
            "inferenceConfig": {
                "maxTokens": MAX_TOKENS,
                "temperature": TEMPERATURE
            }
        }
        
        logger.info(f"Calling Bedrock Nova model: {MODEL_ID}")
        
        # Call Bedrock API
        response = bedrock_client.converse(
            modelId=MODEL_ID,
            **request_payload
        )
        
        # Extract summary from response
        summary = extract_summary_from_response(response)
        
        # Validate summary
        if not summary or len(summary.strip()) == 0:
            logger.warning("Empty summary generated, using fallback")
            # Send notification for empty summary as it might indicate an issue
            logger.error_with_notification(
                "Bedrock returned empty summary",
                category=ErrorCategory.EXTERNAL_SERVICE,
                severity="WARNING",
                model_id=MODEL_ID,
                title=title[:100]
            )
            return generate_fallback_summary(title)
        
        logger.info("Successfully generated summary using Bedrock Nova")
        return summary
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        
        logger.error(f"Bedrock API error - Code: {error_code}, Message: {error_message}")
        
        # Categorize errors for retry logic
        if error_code in ['ThrottlingException', 'ServiceUnavailableException', 'InternalServerException']:
            raise RetryableError(f"Bedrock API retryable error: {error_message}")
        elif error_code in ['ValidationException', 'AccessDeniedException']:
            raise FatalError(f"Bedrock API fatal error: {error_message}")
        else:
            # Default to retryable for unknown errors
            raise RetryableError(f"Bedrock API unknown error: {error_message}")
            
    except Exception as e:
        logger.error(f"Unexpected error in generate_summary: {str(e)}")
        # For unexpected errors, try fallback summary
        try:
            return generate_fallback_summary(title)
        except Exception as fallback_error:
            logger.error(f"Fallback summary generation failed: {str(fallback_error)}")
            raise RetryableError(f"Summary generation failed: {str(e)}")


def format_prompt(content: str, title: str) -> str:
    """
    Create appropriate prompt for article summarization.
    
    Args:
        content: Article content
        title: Article title
        
    Returns:
        Formatted prompt string
    """
    # Truncate content if too long (keep first 3000 characters to stay within token limits)
    max_content_length = 3000
    if len(content) > max_content_length:
        content = content[:max_content_length] + "..."
        logger.info(f"Content truncated to {max_content_length} characters")
    
    prompt = f"""Please provide a concise and informative summary of the following Medium article.

Title: {title}

Article Content:
{content}

Instructions:
- Create a summary that captures the main points and key insights
- Keep the summary between 2-4 sentences
- Focus on the most important information and takeaways
- Write in a clear, professional tone
- Do not include promotional language or calls to action

Summary:"""
    
    return prompt


def extract_summary_from_response(response: Dict[str, Any]) -> str:
    """
    Extract summary text from Bedrock API response.
    
    Args:
        response: Bedrock API response
        
    Returns:
        Extracted summary text
    """
    try:
        # Navigate the response structure for Nova model
        output = response.get('output', {})
        message = output.get('message', {})
        content = message.get('content', [])
        
        if content and len(content) > 0:
            text_content = content[0].get('text', '')
            return text_content.strip()
        
        logger.warning("No content found in Bedrock response")
        return ""
        
    except Exception as e:
        logger.error(f"Error extracting summary from response: {str(e)}")
        return ""


def generate_fallback_summary(title: str) -> str:
    """
    Generate fallback summary when API fails.
    
    Args:
        title: Article title
        
    Returns:
        Fallback summary text
    """
    logger.info("Generating fallback summary")
    return f"Summary unavailable for '{title}'. The article content could not be processed at this time."
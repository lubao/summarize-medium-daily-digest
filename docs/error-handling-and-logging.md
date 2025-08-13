# Error Handling and Logging Documentation

## Overview

The Medium Digest Summarizer implements a comprehensive error handling and logging system that provides structured logging, error categorization, admin notifications, and performance tracking across all Lambda functions.

## Key Features

### 1. Structured Logging
- JSON-formatted log entries with timestamps and context
- Consistent log format across all Lambda functions
- Performance metrics tracking and execution time logging
- Automatic context propagation from Lambda events

### 2. Error Categorization
- Systematic classification of errors into categories:
  - `INPUT_VALIDATION`: Invalid input data or missing required fields
  - `EXTERNAL_SERVICE`: Third-party service failures (Medium, Bedrock, Slack)
  - `AUTHENTICATION`: Credential or permission issues
  - `PROCESSING`: Internal processing logic errors
  - `NETWORK`: Network connectivity issues
  - `RATE_LIMIT`: API rate limiting errors
  - `CONFIGURATION`: Environment or configuration issues
  - `UNKNOWN`: Unclassified errors

### 3. Admin Notification System
- Automatic Slack notifications for critical errors
- Formatted error messages with context and troubleshooting suggestions
- Configurable severity levels (CRITICAL, ERROR, WARNING)
- Failure-safe notification system that doesn't mask original errors

### 4. Performance Tracking
- Execution time monitoring with checkpoints
- Success metrics logging including articles processed
- Performance bottleneck identification
- Resource utilization tracking

## Usage

### Basic Structured Logging

```python
from shared.logging_utils import create_lambda_logger, ErrorCategory

def lambda_handler(event, context):
    # Create logger with Lambda context
    logger = create_lambda_logger("function_name", event, context)
    
    # Log execution start
    logger.log_execution_start("my_function", input_size=len(event))
    
    try:
        # Your processing logic here
        result = process_data(event)
        
        # Log success with metrics
        logger.log_execution_end("my_function", success=True, 
                               metrics={"items_processed": len(result)})
        
        return {"statusCode": 200, "body": result}
        
    except ValidationError as e:
        logger.error("Input validation failed", error=e, 
                    category=ErrorCategory.INPUT_VALIDATION,
                    input_keys=list(event.keys()))
        return {"statusCode": 400, "body": {"error": str(e)}}
        
    except Exception as e:
        logger.critical("Unexpected error occurred", error=e, 
                       category=ErrorCategory.UNKNOWN)
        return {"statusCode": 500, "body": {"error": "Internal server error"}}
```

### Performance Tracking

```python
from shared.logging_utils import PerformanceTracker

def process_articles(articles, logger):
    tracker = PerformanceTracker()
    
    # Record checkpoint
    tracker.checkpoint("validation_start")
    validate_articles(articles)
    tracker.checkpoint("validation_complete")
    
    # Record metrics
    tracker.record_metric("articles_count", len(articles))
    tracker.record_metric("validation_success_rate", 0.95)
    
    # Get all metrics
    metrics = tracker.get_metrics()
    logger.log_success_metrics(metrics, operation="article_processing")
```

### Admin Notifications

```python
from shared.logging_utils import StructuredLogger, ErrorCategory

logger = StructuredLogger("my_function")

# Critical error with automatic notification
logger.critical("Database connection failed", 
                error=connection_error,
                category=ErrorCategory.EXTERNAL_SERVICE,
                database_host="prod-db.example.com")

# Error with explicit notification
logger.error_with_notification("API rate limit exceeded",
                              error=rate_limit_error,
                              category=ErrorCategory.RATE_LIMIT,
                              severity="WARNING",
                              api_endpoint="/api/v1/data")
```

### Retry Logic with Logging

```python
from shared.error_handling import exponential_backoff_retry, NetworkError
from shared.logging_utils import StructuredLogger

logger = StructuredLogger("api_client")

@exponential_backoff_retry(max_retries=3, base_delay=1.0)
def call_external_api(url):
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.log_retry_attempt("call_external_api", 1, 3, 
                               TimeoutError("Request timeout"), 2.0)
        raise NetworkError("API request timeout")
    except requests.exceptions.ConnectionError as e:
        logger.log_retry_attempt("call_external_api", 1, 3, e, 2.0)
        raise NetworkError(f"Connection failed: {str(e)}")
```

## Error Categories and Handling

### Input Validation Errors
- **When to use**: Invalid request format, missing required fields, malformed data
- **Handling**: Log error, return 400 status, no retry
- **Example**: Missing article URL in fetch request

```python
if not article_url:
    logger.error("Missing article URL", 
                category=ErrorCategory.INPUT_VALIDATION,
                event_keys=list(event.keys()))
    raise ValidationError("Article URL is required")
```

### External Service Errors
- **When to use**: Third-party API failures, service unavailable
- **Handling**: Log error, implement retry logic, send admin notification for persistent failures
- **Example**: Medium API returning 500 error

```python
if response.status_code >= 500:
    logger.error("Medium API server error", 
                category=ErrorCategory.EXTERNAL_SERVICE,
                status_code=response.status_code,
                url=article_url)
    raise NetworkError(f"Server error: {response.status_code}")
```

### Authentication Errors
- **When to use**: Invalid credentials, expired tokens, permission denied
- **Handling**: Log critical error, send admin notification, no retry
- **Example**: Invalid Medium cookies

```python
if response.status_code == 401:
    logger.critical("Medium authentication failed", 
                   category=ErrorCategory.AUTHENTICATION,
                   status_code=response.status_code)
    raise AuthenticationError("Invalid Medium credentials")
```

## Admin Notification System

### Notification Triggers
- All `CRITICAL` level logs automatically send notifications
- Explicit notifications via `error_with_notification()` method
- Configurable severity levels affect message formatting

### Message Format
Admin notifications include:
- **Severity**: CRITICAL, ERROR, WARNING
- **Message**: Human-readable error description
- **Error Details**: Exception type and message
- **Category**: Error classification
- **Timestamp**: UTC timestamp
- **Key Details**: Important context (function name, request ID, URLs)
- **Additional Context**: Extra debugging information
- **Suggested Actions**: Troubleshooting recommendations

### Example Notification
```
🚨 CRITICAL Alert - Medium Digest Summarizer

*Severity:* CRITICAL
*Message:* Failed to retrieve Medium cookies
*Error Type:* SecretsManagerError
*Error Details:* Secret 'medium-cookies' not found
*Category:* Authentication
*Timestamp:* 2025-01-15T10:30:45.123Z
*Key Details:* Function Name: fetch_articles, Request Id: req-abc123, Url: https://medium.com/article
*Suggested Actions:* Verify credentials in Secrets Manager and check IAM permissions
```

### Notification Configuration
- Webhook URL stored in AWS Secrets Manager as `slack-webhook-url`
- Failure-safe: Notification failures don't interrupt main processing
- Automatic retry for webhook failures

## Performance Metrics

### Tracked Metrics
- **Execution Time**: Total function execution time
- **Checkpoints**: Intermediate timing measurements
- **Success Rates**: Processing success percentages
- **Resource Usage**: Memory and processing statistics
- **Error Rates**: Categorized error frequencies

### Metrics Collection
```python
# In Lambda functions
metrics = {
    "articles_processed": 5,
    "successful_summaries": 4,
    "failed_summaries": 1,
    "average_summary_length": 150,
    "total_execution_time": 45.2
}

logger.log_success_metrics(metrics, operation="batch_summarization")
```

## Integration with Lambda Functions

### Parse Email Lambda
- Logs email content size and parsing results
- Tracks URL extraction and validation metrics
- Sends notifications for invalid URL patterns

### Fetch Articles Lambda
- Monitors Medium API response times and status codes
- Tracks authentication failures and rate limiting
- Logs article content extraction success rates

### Summarize Lambda
- Monitors Bedrock API performance and failures
- Tracks summary generation success rates
- Logs fallback summary usage

### Send to Slack Lambda
- Monitors webhook delivery success rates
- Tracks message formatting and payload sizes
- Logs Slack API response codes

### Trigger Lambda
- Monitors S3 event processing
- Tracks Step Function execution initiation
- Logs workflow orchestration metrics

## Testing

### Error Scenario Testing
The system includes comprehensive tests for:
- Admin notification delivery and formatting
- Error categorization accuracy
- Performance metrics collection
- Structured logging format consistency
- Retry logic with error handling

### Test Categories
1. **Unit Tests**: Individual component testing
2. **Integration Tests**: End-to-end error scenarios
3. **Performance Tests**: Metrics collection validation
4. **Notification Tests**: Slack webhook delivery

### Running Tests
```bash
# Run all error handling tests
python -m pytest tests/test_error_handling_notifications.py -v

# Run specific test category
python -m pytest tests/test_error_handling_notifications.py::TestAdminNotifications -v
```

## Best Practices

### 1. Error Context
Always include relevant context in error logs:
```python
logger.error("Processing failed", 
            error=e,
            category=ErrorCategory.PROCESSING,
            article_url=url,
            article_title=title[:50],
            processing_step="content_extraction")
```

### 2. Performance Tracking
Use checkpoints for long-running operations:
```python
tracker = PerformanceTracker()
tracker.checkpoint("start_processing")
# ... processing logic ...
tracker.checkpoint("processing_complete")
metrics = tracker.get_metrics()
```

### 3. Notification Severity
Choose appropriate severity levels:
- **CRITICAL**: System failures, authentication issues, data corruption
- **ERROR**: Processing failures, external service errors
- **WARNING**: Degraded performance, fallback usage, rate limiting

### 4. Error Recovery
Implement graceful degradation:
```python
try:
    summary = generate_ai_summary(content)
except Exception as e:
    logger.error_with_notification("AI summary failed, using fallback",
                                  error=e, severity="WARNING")
    summary = generate_fallback_summary(title)
```

## Monitoring and Alerting

### CloudWatch Integration
- All structured logs are automatically sent to CloudWatch
- JSON format enables easy querying and filtering
- Custom metrics can be extracted from log data

### Slack Integration
- Real-time error notifications to development team
- Formatted messages with actionable information
- Automatic escalation for critical issues

### Performance Monitoring
- Execution time trends and anomaly detection
- Success rate monitoring and alerting
- Resource utilization tracking

## Troubleshooting

### Common Issues

1. **Missing Admin Notifications**
   - Check Slack webhook URL in Secrets Manager
   - Verify IAM permissions for Secrets Manager access
   - Check CloudWatch logs for notification failures

2. **Incomplete Log Context**
   - Ensure logger is created with proper context
   - Verify all error handlers include relevant information
   - Check for truncated log messages in CloudWatch

3. **Performance Metrics Missing**
   - Verify PerformanceTracker is properly initialized
   - Check that metrics are recorded before function exit
   - Ensure checkpoints are called at appropriate times

### Debug Mode
Enable debug logging for detailed troubleshooting:
```python
logger.debug("Detailed processing information", 
            step="validation",
            input_data=sanitized_input,
            intermediate_results=results)
```

This comprehensive error handling and logging system ensures robust monitoring, quick issue identification, and effective troubleshooting across the entire Medium Digest Summarizer application.
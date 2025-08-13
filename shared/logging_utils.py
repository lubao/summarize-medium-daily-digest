"""
Enhanced logging utilities with structured logging, error categorization, and admin notifications.
"""
import json
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import boto3
from botocore.exceptions import ClientError

# Import shared utilities
from .error_handling import FatalError, RetryableError, ValidationError, AuthenticationError
from .secrets_manager import get_secret


class ErrorCategory(Enum):
    """Error categories for structured error handling."""
    INPUT_VALIDATION = "input_validation"
    EXTERNAL_SERVICE = "external_service"
    AUTHENTICATION = "authentication"
    PROCESSING = "processing"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class LogLevel(Enum):
    """Log levels for structured logging."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredLogger:
    """Enhanced logger with structured logging and error categorization."""
    
    def __init__(self, name: str, context: Optional[Dict[str, Any]] = None):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name (typically __name__)
            context: Additional context to include in all log messages
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # Set up JSON formatter for structured logging
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = StructuredFormatter()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self.context = context or {}
        self.start_time = time.time()
        
    def _create_log_entry(
        self,
        level: LogLevel,
        message: str,
        error: Optional[Exception] = None,
        category: Optional[ErrorCategory] = None,
        metrics: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create structured log entry.
        
        Args:
            level: Log level
            message: Log message
            error: Exception object if applicable
            category: Error category if applicable
            metrics: Performance metrics
            **kwargs: Additional context
            
        Returns:
            Structured log entry dictionary
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.value,
            "message": message,
            "context": {**self.context, **kwargs},
            "execution_time": round(time.time() - self.start_time, 3)
        }
        
        if error:
            log_entry["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "category": category.value if category else self._categorize_error(error).value
            }
        
        if metrics:
            log_entry["metrics"] = metrics
            
        return log_entry
    
    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """
        Automatically categorize error based on exception type.
        
        Args:
            error: Exception to categorize
            
        Returns:
            Error category
        """
        if isinstance(error, ValidationError):
            return ErrorCategory.INPUT_VALIDATION
        elif isinstance(error, AuthenticationError):
            return ErrorCategory.AUTHENTICATION
        elif isinstance(error, RetryableError):
            return ErrorCategory.EXTERNAL_SERVICE
        elif isinstance(error, ClientError):
            error_code = error.response.get('Error', {}).get('Code', '')
            if 'Auth' in error_code or 'Credential' in error_code:
                return ErrorCategory.AUTHENTICATION
            elif 'Throttling' in error_code or 'Limit' in error_code:
                return ErrorCategory.RATE_LIMIT
            else:
                return ErrorCategory.EXTERNAL_SERVICE
        elif 'network' in str(error).lower() or 'connection' in str(error).lower():
            return ErrorCategory.NETWORK
        else:
            return ErrorCategory.UNKNOWN
    
    def info(self, message: str, metrics: Optional[Dict[str, Any]] = None, **kwargs):
        """Log info message with structured format."""
        log_entry = self._create_log_entry(LogLevel.INFO, message, metrics=metrics, **kwargs)
        self.logger.info(json.dumps(log_entry))
    
    def warning(self, message: str, error: Optional[Exception] = None, 
                category: Optional[ErrorCategory] = None, **kwargs):
        """Log warning message with structured format."""
        log_entry = self._create_log_entry(LogLevel.WARNING, message, error=error, 
                                         category=category, **kwargs)
        self.logger.warning(json.dumps(log_entry))
    
    def error(self, message: str, error: Optional[Exception] = None, 
              category: Optional[ErrorCategory] = None, **kwargs):
        """Log error message with structured format."""
        log_entry = self._create_log_entry(LogLevel.ERROR, message, error=error, 
                                         category=category, **kwargs)
        self.logger.error(json.dumps(log_entry))
    
    def critical(self, message: str, error: Optional[Exception] = None, 
                 category: Optional[ErrorCategory] = None, send_notification: bool = True, **kwargs):
        """Log critical message with structured format and send admin notification."""
        log_entry = self._create_log_entry(LogLevel.CRITICAL, message, error=error, 
                                         category=category, **kwargs)
        self.logger.critical(json.dumps(log_entry))
        
        # Send admin notification for critical errors
        if send_notification:
            try:
                # Include context from logger in notification
                notification_context = {**self.context, **kwargs}
                send_admin_notification(message, error, category, "CRITICAL", **notification_context)
            except Exception as notification_error:
                self.logger.error(f"Failed to send admin notification: {notification_error}")
    
    def error_with_notification(self, message: str, error: Optional[Exception] = None, 
                               category: Optional[ErrorCategory] = None, severity: str = "ERROR", **kwargs):
        """Log error message and send admin notification."""
        log_entry = self._create_log_entry(LogLevel.ERROR, message, error=error, 
                                         category=category, **kwargs)
        self.logger.error(json.dumps(log_entry))
        
        # Send admin notification
        try:
            # Include context from logger in notification
            notification_context = {**self.context, **kwargs}
            send_admin_notification(message, error, category, severity, **notification_context)
        except Exception as notification_error:
            self.logger.error(f"Failed to send admin notification: {notification_error}")
    
    def debug(self, message: str, **kwargs):
        """Log debug message with structured format."""
        log_entry = self._create_log_entry(LogLevel.DEBUG, message, **kwargs)
        self.logger.debug(json.dumps(log_entry))
    
    def log_execution_start(self, function_name: str, **kwargs):
        """Log function execution start."""
        self.info(f"Starting {function_name} execution", function=function_name, **kwargs)
    
    def log_execution_end(self, function_name: str, success: bool = True, 
                         metrics: Optional[Dict[str, Any]] = None, **kwargs):
        """Log function execution end with metrics."""
        execution_time = time.time() - self.start_time
        final_metrics = {"execution_time_seconds": round(execution_time, 3)}
        if metrics:
            final_metrics.update(metrics)
        
        if success:
            self.info(f"Completed {function_name} execution successfully", 
                     metrics=final_metrics, function=function_name, **kwargs)
        else:
            self.error(f"Failed {function_name} execution", 
                      metrics=final_metrics, function=function_name, **kwargs)
    
    def log_retry_attempt(self, function_name: str, attempt: int, max_attempts: int, 
                         error: Exception, delay: float):
        """Log retry attempt."""
        self.warning(
            f"Retry attempt {attempt}/{max_attempts} for {function_name}",
            error=error,
            category=self._categorize_error(error),
            function=function_name,
            attempt=attempt,
            max_attempts=max_attempts,
            retry_delay=delay
        )
    
    def log_success_metrics(self, metrics: Dict[str, Any], **kwargs):
        """Log success metrics."""
        self.info("Success metrics recorded", metrics=metrics, **kwargs)


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging."""
    
    def format(self, record):
        """Format log record as JSON if it's already structured, otherwise use default format."""
        try:
            # If the message is already JSON, return it as-is
            json.loads(record.getMessage())
            return record.getMessage()
        except (json.JSONDecodeError, ValueError):
            # If not JSON, use default formatting
            return super().format(record)


def send_admin_notification(
    message: str,
    error: Optional[Exception] = None,
    category: Optional[ErrorCategory] = None,
    severity: str = "ERROR",
    **context
) -> None:
    """
    Send critical error notifications to administrators via Slack.
    
    Args:
        message: Error message
        error: Exception object if applicable
        category: Error category
        severity: Severity level (CRITICAL, ERROR, WARNING)
        **context: Additional context information
    """
    try:
        # Get Slack webhook URL from Secrets Manager
        slack_webhook_url = get_secret("slack-webhook-url")
        
        # Format error message for Slack
        slack_message = format_admin_notification(message, error, category, severity, **context)
        
        # Send to Slack
        import requests
        
        # Choose color and emoji based on severity
        color_map = {
            "CRITICAL": "danger",
            "ERROR": "warning", 
            "WARNING": "good"
        }
        
        emoji_map = {
            "CRITICAL": "🚨",
            "ERROR": "⚠️",
            "WARNING": "⚡"
        }
        
        color = color_map.get(severity, "warning")
        emoji = emoji_map.get(severity, "⚠️")
        
        payload = {
            "text": f"{emoji} {severity} Alert - Medium Digest Summarizer",
            "attachments": [
                {
                    "color": color,
                    "fields": [
                        {
                            "title": "Error Details",
                            "value": slack_message,
                            "short": False
                        }
                    ],
                    "footer": "Medium Digest Summarizer Admin Notifications",
                    "ts": int(time.time())
                }
            ]
        }
        
        response = requests.post(
            slack_webhook_url,
            json=payload,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        response.raise_for_status()
        
        # Log successful notification
        notification_logger = logging.getLogger(__name__)
        notification_logger.info(f"Successfully sent {severity} admin notification to Slack")
        
    except Exception as notification_error:
        # Log notification failure but don't raise to avoid masking original error
        notification_logger = logging.getLogger(__name__)
        notification_logger.error(f"Failed to send admin notification: {notification_error}", exc_info=True)


def format_admin_notification(
    message: str,
    error: Optional[Exception] = None,
    category: Optional[ErrorCategory] = None,
    severity: str = "ERROR",
    **context
) -> str:
    """
    Format error message for admin notifications.
    
    Args:
        message: Error message
        error: Exception object if applicable
        category: Error category
        severity: Severity level
        **context: Additional context information
        
    Returns:
        Formatted error message
    """
    lines = [f"*Severity:* {severity}"]
    lines.append(f"*Message:* {message}")
    
    if error:
        lines.append(f"*Error Type:* {type(error).__name__}")
        lines.append(f"*Error Details:* {str(error)}")
    
    if category:
        lines.append(f"*Category:* {category.value.replace('_', ' ').title()}")
    
    # Add timestamp
    lines.append(f"*Timestamp:* {datetime.utcnow().isoformat()}Z")
    
    # Add context information
    if context:
        important_context = {}
        general_context = {}
        
        # Separate important context from general context
        important_keys = ['function_name', 'request_id', 'url', 'bucket', 'key', 'execution_arn', 'status_code']
        
        for key, value in context.items():
            if key not in ['timestamp', 'level', 'message', 'error', 'metrics']:
                if key in important_keys:
                    important_context[key] = value
                else:
                    general_context[key] = value
        
        # Add important context first
        if important_context:
            context_items = []
            for key, value in important_context.items():
                formatted_key = key.replace('_', ' ').title()
                context_items.append(f"{formatted_key}: {value}")
            lines.append(f"*Key Details:* {', '.join(context_items)}")
        
        # Add general context if present
        if general_context:
            context_items = []
            for key, value in general_context.items():
                formatted_key = key.replace('_', ' ').title()
                # Truncate long values
                if isinstance(value, str) and len(value) > 100:
                    value = value[:97] + "..."
                context_items.append(f"{formatted_key}: {value}")
            
            if context_items:
                lines.append(f"*Additional Context:* {', '.join(context_items)}")
    
    # Add troubleshooting suggestions based on error category
    if category:
        suggestions = get_troubleshooting_suggestions(category, error)
        if suggestions:
            lines.append(f"*Suggested Actions:* {suggestions}")
    
    return "\n".join(lines)


def get_troubleshooting_suggestions(category: ErrorCategory, error: Optional[Exception] = None) -> str:
    """
    Get troubleshooting suggestions based on error category.
    
    Args:
        category: Error category
        error: Exception object if applicable
        
    Returns:
        Troubleshooting suggestions string
    """
    suggestions_map = {
        ErrorCategory.INPUT_VALIDATION: "Check input data format and required fields",
        ErrorCategory.AUTHENTICATION: "Verify credentials in Secrets Manager and check IAM permissions",
        ErrorCategory.EXTERNAL_SERVICE: "Check service status and retry limits, verify network connectivity",
        ErrorCategory.RATE_LIMIT: "Implement exponential backoff and reduce request frequency",
        ErrorCategory.NETWORK: "Check network connectivity and DNS resolution",
        ErrorCategory.CONFIGURATION: "Verify environment variables and resource configurations",
        ErrorCategory.PROCESSING: "Review input data and processing logic"
    }
    
    base_suggestion = suggestions_map.get(category, "Review logs and check system status")
    
    # Add specific suggestions based on error type
    if error:
        error_type = type(error).__name__
        if "Timeout" in error_type:
            base_suggestion += ", increase timeout values"
        elif "Permission" in error_type or "Access" in error_type:
            base_suggestion += ", check IAM roles and policies"
        elif "NotFound" in error_type:
            base_suggestion += ", verify resource exists and paths are correct"
    
    return base_suggestion


class PerformanceTracker:
    """Utility for tracking performance metrics."""
    
    def __init__(self):
        """Initialize performance tracker."""
        self.start_time = time.time()
        self.checkpoints = {}
        self.metrics = {}
    
    def checkpoint(self, name: str):
        """Record a performance checkpoint."""
        self.checkpoints[name] = time.time()
    
    def get_elapsed_time(self, checkpoint: Optional[str] = None) -> float:
        """Get elapsed time since start or checkpoint."""
        reference_time = self.checkpoints.get(checkpoint, self.start_time)
        return time.time() - reference_time
    
    def record_metric(self, name: str, value: Union[int, float, str]):
        """Record a performance metric."""
        self.metrics[name] = value
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get all recorded metrics."""
        total_time = time.time() - self.start_time
        return {
            **self.metrics,
            "total_execution_time": round(total_time, 3),
            "checkpoints": {
                name: round(timestamp - self.start_time, 3)
                for name, timestamp in self.checkpoints.items()
            }
        }


def create_lambda_logger(function_name: str, event: Dict[str, Any], 
                        context: Any) -> StructuredLogger:
    """
    Create a structured logger for Lambda functions with context.
    
    Args:
        function_name: Name of the Lambda function
        event: Lambda event object
        context: Lambda context object
        
    Returns:
        Configured StructuredLogger instance
    """
    lambda_context = {
        "function_name": function_name,
        "request_id": getattr(context, 'aws_request_id', 'unknown'),
        "function_version": getattr(context, 'function_version', 'unknown'),
        "memory_limit": getattr(context, 'memory_limit_in_mb', 'unknown'),
        "remaining_time": getattr(context, 'get_remaining_time_in_millis', lambda: 0)()
    }
    
    return StructuredLogger(function_name, lambda_context)


# Convenience functions for backward compatibility
def log_error_with_category(logger: StructuredLogger, message: str, error: Exception, 
                           category: ErrorCategory, **kwargs):
    """Log error with specific category."""
    logger.error(message, error=error, category=category, **kwargs)


def log_success_with_metrics(logger: StructuredLogger, message: str, 
                           metrics: Dict[str, Any], **kwargs):
    """Log success message with metrics."""
    logger.info(message, metrics=metrics, **kwargs)
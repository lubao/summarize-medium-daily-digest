"""
Error handling utilities with retry logic and exponential backoff.
"""
import logging
import time
from functools import wraps
from typing import Any, Callable, List, Optional, Type, Union

logger = logging.getLogger(__name__)


class RetryableError(Exception):
    """Base exception for errors that can be retried."""
    pass


class FatalError(Exception):
    """Base exception for errors that should not be retried."""
    pass


class RateLimitError(RetryableError):
    """Exception for rate limiting errors."""
    pass


class NetworkError(RetryableError):
    """Exception for network-related errors."""
    pass


class AuthenticationError(FatalError):
    """Exception for authentication failures."""
    pass


class ValidationError(FatalError):
    """Exception for input validation errors."""
    pass


def exponential_backoff_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: Optional[List[Type[Exception]]] = None,
    fatal_exceptions: Optional[List[Type[Exception]]] = None
):
    """
    Decorator that implements exponential backoff retry logic.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Factor by which delay increases after each retry
        retryable_exceptions: List of exception types that should trigger retries
        fatal_exceptions: List of exception types that should not be retried
        
    Returns:
        Decorated function with retry logic
    """
    if retryable_exceptions is None:
        retryable_exceptions = [RetryableError, RateLimitError, NetworkError]
    
    if fatal_exceptions is None:
        fatal_exceptions = [FatalError, AuthenticationError, ValidationError]
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        logger.info(f"{func.__name__} succeeded after {attempt} retries")
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    # Check if this is a fatal error that shouldn't be retried
                    if any(isinstance(e, exc_type) for exc_type in fatal_exceptions):
                        logger.error(f"{func.__name__} failed with fatal error: {str(e)}")
                        raise e
                    
                    # Check if this is a retryable error
                    is_retryable = any(isinstance(e, exc_type) for exc_type in retryable_exceptions)
                    
                    if not is_retryable and attempt == 0:
                        # If it's not explicitly retryable and this is the first attempt,
                        # treat it as retryable for backwards compatibility
                        is_retryable = True
                    
                    if not is_retryable:
                        logger.error(f"{func.__name__} failed with non-retryable error: {str(e)}")
                        raise e
                    
                    if attempt < max_retries:
                        # Calculate delay with exponential backoff
                        delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                        
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {str(e)}. "
                            f"Retrying in {delay:.2f} seconds..."
                        )
                        
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"{func.__name__} failed after {max_retries + 1} attempts: {str(e)}"
                        )
            
            # If we get here, all retries have been exhausted
            raise last_exception
        
        return wrapper
    return decorator


def handle_retryable_error(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0
) -> Any:
    """
    Execute a function with retry logic for retryable errors.
    
    Args:
        func: Function to execute
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries in seconds
        backoff_factor: Factor by which delay increases after each retry
        
    Returns:
        Result of the function execution
        
    Raises:
        Exception: The last exception if all retries fail
    """
    @exponential_backoff_retry(
        max_retries=max_retries,
        base_delay=base_delay,
        backoff_factor=backoff_factor
    )
    def wrapper():
        return func()
    
    return wrapper()


def handle_fatal_error(error: Exception, context: str) -> dict:
    """
    Handle fatal errors by logging and returning appropriate error response.
    
    Args:
        error: The exception that occurred
        context: Context information about where the error occurred
        
    Returns:
        Dictionary containing error response
    """
    error_message = f"Fatal error in {context}: {str(error)}"
    logger.error(error_message, exc_info=True)
    
    return {
        "statusCode": 500,
        "body": {
            "error": "Internal server error",
            "message": error_message,
            "context": context
        }
    }


def send_admin_notification(error: Exception, context: str, severity: str = "ERROR") -> None:
    """
    Send critical error notifications to administrators.
    
    Args:
        error: The exception that occurred
        context: Context information about where the error occurred
        severity: Severity level of the error (ERROR, CRITICAL, WARNING)
    """
    # For now, just log the error. In a real implementation, this would
    # send notifications via SNS, email, or Slack
    log_message = f"[{severity}] Admin notification - {context}: {str(error)}"
    
    if severity == "CRITICAL":
        logger.critical(log_message, exc_info=True)
    elif severity == "ERROR":
        logger.error(log_message, exc_info=True)
    elif severity == "WARNING":
        logger.warning(log_message, exc_info=True)
    else:
        logger.info(log_message, exc_info=True)


class ErrorHandler:
    """Centralized error handling utility class."""
    
    @staticmethod
    def handle_retryable_error(func: Callable, max_retries: int = 3) -> Any:
        """
        Handle retryable errors with exponential backoff.
        
        Args:
            func: Function to execute with retry logic
            max_retries: Maximum number of retry attempts
            
        Returns:
            Result of the function execution
        """
        return handle_retryable_error(func, max_retries)
    
    @staticmethod
    def handle_fatal_error(error: Exception, context: str) -> dict:
        """
        Handle fatal errors by logging and returning error response.
        
        Args:
            error: The exception that occurred
            context: Context information
            
        Returns:
            Error response dictionary
        """
        return handle_fatal_error(error, context)
    
    @staticmethod
    def send_admin_notification(error: Exception, context: str = "") -> None:
        """
        Send critical error notifications to administrators.
        
        Args:
            error: The exception that occurred
            context: Context information
        """
        send_admin_notification(error, context, "CRITICAL")


# Convenience decorators for common retry patterns
def medium_api_retry(func: Callable) -> Callable:
    """Decorator for Medium API calls with appropriate retry settings."""
    return exponential_backoff_retry(
        max_retries=3,
        base_delay=1.0,
        backoff_factor=2.0,
        retryable_exceptions=[RetryableError, RateLimitError, NetworkError]
    )(func)


def bedrock_api_retry(func: Callable) -> Callable:
    """Decorator for Bedrock API calls with appropriate retry settings."""
    return exponential_backoff_retry(
        max_retries=3,
        base_delay=2.0,
        backoff_factor=2.0,
        retryable_exceptions=[RetryableError, NetworkError]
    )(func)


def slack_webhook_retry(func: Callable) -> Callable:
    """Decorator for Slack webhook calls with appropriate retry settings."""
    return exponential_backoff_retry(
        max_retries=3,
        base_delay=1.0,
        backoff_factor=2.0,
        retryable_exceptions=[RetryableError, NetworkError]
    )(func)
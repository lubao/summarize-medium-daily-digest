"""
Unit tests for error handling utilities.
"""
import time
import pytest
from unittest.mock import Mock, patch

from shared.error_handling import (
    exponential_backoff_retry,
    handle_retryable_error,
    handle_fatal_error,
    send_admin_notification,
    ErrorHandler,
    RetryableError,
    FatalError,
    RateLimitError,
    NetworkError,
    AuthenticationError,
    ValidationError,
    medium_api_retry,
    bedrock_api_retry,
    slack_webhook_retry
)


class TestExponentialBackoffRetry:
    """Test cases for the exponential_backoff_retry decorator."""
    
    def test_successful_execution_no_retry(self):
        """Test successful function execution without retries."""
        @exponential_backoff_retry(max_retries=3)
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success"
    
    def test_successful_execution_after_retries(self):
        """Test successful function execution after some retries."""
        call_count = 0
        
        @exponential_backoff_retry(max_retries=3, base_delay=0.01)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("Temporary error")
            return "success"
        
        result = test_function()
        assert result == "success"
        assert call_count == 3
    
    def test_max_retries_exceeded(self):
        """Test behavior when max retries are exceeded."""
        @exponential_backoff_retry(max_retries=2, base_delay=0.01)
        def test_function():
            raise RetryableError("Persistent error")
        
        with pytest.raises(RetryableError):
            test_function()
    
    def test_fatal_error_no_retry(self):
        """Test that fatal errors are not retried."""
        call_count = 0
        
        @exponential_backoff_retry(max_retries=3)
        def test_function():
            nonlocal call_count
            call_count += 1
            raise AuthenticationError("Fatal error")
        
        with pytest.raises(AuthenticationError):
            test_function()
        
        assert call_count == 1
    
    def test_custom_retryable_exceptions(self):
        """Test with custom retryable exceptions."""
        call_count = 0
        
        @exponential_backoff_retry(
            max_retries=2,
            base_delay=0.01,
            retryable_exceptions=[ValueError]
        )
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Retryable error")
            return "success"
        
        result = test_function()
        assert result == "success"
        assert call_count == 3
    
    def test_custom_fatal_exceptions(self):
        """Test with custom fatal exceptions."""
        call_count = 0
        
        @exponential_backoff_retry(
            max_retries=3,
            fatal_exceptions=[ValueError]
        )
        def test_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Fatal error")
        
        with pytest.raises(ValueError):
            test_function()
        
        assert call_count == 1
    
    @patch('time.sleep')
    def test_exponential_backoff_timing(self, mock_sleep):
        """Test that exponential backoff timing is correct."""
        call_count = 0
        
        @exponential_backoff_retry(
            max_retries=3,
            base_delay=1.0,
            backoff_factor=2.0
        )
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:  # Changed to ensure it fails after all retries
                raise RetryableError("Temporary error")
            return "success"
        
        with pytest.raises(RetryableError):
            test_function()
        
        # Check that sleep was called with correct delays
        expected_delays = [1.0, 2.0, 4.0]
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert actual_delays == expected_delays
    
    @patch('time.sleep')
    def test_max_delay_limit(self, mock_sleep):
        """Test that delay is capped at max_delay."""
        call_count = 0
        
        @exponential_backoff_retry(
            max_retries=5,
            base_delay=1.0,
            backoff_factor=2.0,
            max_delay=3.0
        )
        def test_function():
            nonlocal call_count
            call_count += 1
            raise RetryableError("Temporary error")
        
        with pytest.raises(RetryableError):
            test_function()
        
        # Check that delays are capped at max_delay
        actual_delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert all(delay <= 3.0 for delay in actual_delays)


class TestHandleRetryableError:
    """Test cases for the handle_retryable_error function."""
    
    def test_successful_execution(self):
        """Test successful function execution."""
        def test_function():
            return "success"
        
        result = handle_retryable_error(test_function)
        assert result == "success"
    
    @patch('time.sleep')
    def test_retry_on_error(self, mock_sleep):
        """Test retry behavior on error."""
        call_count = 0
        
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("Temporary error")  # Use RetryableError instead of Exception
            return "success"
        
        result = handle_retryable_error(test_function, max_retries=3, base_delay=0.01)
        assert result == "success"
        assert call_count == 3


class TestHandleFatalError:
    """Test cases for the handle_fatal_error function."""
    
    @patch('shared.error_handling.logger')
    def test_handle_fatal_error(self, mock_logger):
        """Test fatal error handling."""
        error = ValueError("Test error")
        context = "test_function"
        
        result = handle_fatal_error(error, context)
        
        expected_result = {
            "statusCode": 500,
            "body": {
                "error": "Internal server error",
                "message": "Fatal error in test_function: Test error",
                "context": "test_function"
            }
        }
        
        assert result == expected_result
        mock_logger.error.assert_called_once()


class TestSendAdminNotification:
    """Test cases for the send_admin_notification function."""
    
    @patch('shared.error_handling.logger')
    def test_send_admin_notification_error(self, mock_logger):
        """Test sending admin notification with ERROR severity."""
        error = ValueError("Test error")
        context = "test_function"
        
        send_admin_notification(error, context, "ERROR")
        
        mock_logger.error.assert_called_once()
        args, kwargs = mock_logger.error.call_args
        assert "Admin notification - test_function: Test error" in args[0]
        assert kwargs.get('exc_info') is True
    
    @patch('shared.error_handling.logger')
    def test_send_admin_notification_critical(self, mock_logger):
        """Test sending admin notification with CRITICAL severity."""
        error = ValueError("Test error")
        context = "test_function"
        
        send_admin_notification(error, context, "CRITICAL")
        
        mock_logger.critical.assert_called_once()
    
    @patch('shared.error_handling.logger')
    def test_send_admin_notification_warning(self, mock_logger):
        """Test sending admin notification with WARNING severity."""
        error = ValueError("Test error")
        context = "test_function"
        
        send_admin_notification(error, context, "WARNING")
        
        mock_logger.warning.assert_called_once()


class TestErrorHandler:
    """Test cases for the ErrorHandler class."""
    
    def test_handle_retryable_error(self):
        """Test ErrorHandler.handle_retryable_error method."""
        def test_function():
            return "success"
        
        result = ErrorHandler.handle_retryable_error(test_function)
        assert result == "success"
    
    @patch('shared.error_handling.handle_fatal_error')
    def test_handle_fatal_error(self, mock_handle_fatal_error):
        """Test ErrorHandler.handle_fatal_error method."""
        error = ValueError("Test error")
        context = "test_context"
        
        ErrorHandler.handle_fatal_error(error, context)
        
        mock_handle_fatal_error.assert_called_once_with(error, context)
    
    @patch('shared.error_handling.send_admin_notification')
    def test_send_admin_notification(self, mock_send_admin_notification):
        """Test ErrorHandler.send_admin_notification method."""
        error = ValueError("Test error")
        context = "test_context"
        
        ErrorHandler.send_admin_notification(error, context)
        
        mock_send_admin_notification.assert_called_once_with(error, context, "CRITICAL")


class TestSpecializedRetryDecorators:
    """Test cases for specialized retry decorators."""
    
    def test_medium_api_retry(self):
        """Test medium_api_retry decorator."""
        @medium_api_retry
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success"
    
    def test_bedrock_api_retry(self):
        """Test bedrock_api_retry decorator."""
        @bedrock_api_retry
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success"
    
    def test_slack_webhook_retry(self):
        """Test slack_webhook_retry decorator."""
        @slack_webhook_retry
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success"


class TestCustomExceptions:
    """Test cases for custom exception classes."""
    
    def test_retryable_error(self):
        """Test RetryableError exception."""
        with pytest.raises(RetryableError):
            raise RetryableError("Test error")
    
    def test_fatal_error(self):
        """Test FatalError exception."""
        with pytest.raises(FatalError):
            raise FatalError("Test error")
    
    def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        with pytest.raises(RateLimitError):
            raise RateLimitError("Test error")
        
        # Verify it's also a RetryableError
        assert issubclass(RateLimitError, RetryableError)
    
    def test_network_error(self):
        """Test NetworkError exception."""
        with pytest.raises(NetworkError):
            raise NetworkError("Test error")
        
        # Verify it's also a RetryableError
        assert issubclass(NetworkError, RetryableError)
    
    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("Test error")
        
        # Verify it's also a FatalError
        assert issubclass(AuthenticationError, FatalError)
    
    def test_validation_error(self):
        """Test ValidationError exception."""
        with pytest.raises(ValidationError):
            raise ValidationError("Test error")
        
        # Verify it's also a FatalError
        assert issubclass(ValidationError, FatalError)
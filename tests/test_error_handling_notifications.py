"""
Integration tests for error handling and admin notifications.
"""
import json
import pytest
import time
import requests
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any

# Import shared utilities
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logging_utils import (
    StructuredLogger, ErrorCategory, send_admin_notification, 
    format_admin_notification, create_lambda_logger
)
from shared.error_handling import (
    ValidationError, AuthenticationError, NetworkError, RateLimitError,
    exponential_backoff_retry
)


class TestAdminNotifications:
    """Test admin notification system."""
    
    @patch('shared.logging_utils.get_secret')
    @patch('requests.post')
    def test_send_admin_notification_success(self, mock_post, mock_get_secret):
        """Test successful admin notification sending."""
        # Setup mocks
        mock_get_secret.return_value = "https://hooks.slack.com/test/webhook"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test notification
        error = ValidationError("Test validation error")
        send_admin_notification(
            "Test error message",
            error=error,
            category=ErrorCategory.INPUT_VALIDATION,
            severity="ERROR",
            function_name="test_function",
            request_id="test-123"
        )
        
        # Verify webhook was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL
        assert call_args[1]['json']['text'] == "⚠️ ERROR Alert - Medium Digest Summarizer"
        
        # Check payload structure
        payload = call_args[1]['json']
        assert 'attachments' in payload
        assert len(payload['attachments']) == 1
        
        attachment = payload['attachments'][0]
        assert attachment['color'] == 'warning'
        assert 'fields' in attachment
        assert len(attachment['fields']) == 1
        
        field = attachment['fields'][0]
        assert field['title'] == 'Error Details'
        assert 'Test error message' in field['value']
        assert 'ValidationError' in field['value']
        assert 'Input Validation' in field['value']
    
    @patch('shared.logging_utils.get_secret')
    @patch('requests.post')
    def test_send_admin_notification_critical(self, mock_post, mock_get_secret):
        """Test critical admin notification with different formatting."""
        # Setup mocks
        mock_get_secret.return_value = "https://hooks.slack.com/test/webhook"
        mock_response = Mock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        
        # Test critical notification
        error = Exception("Critical system failure")
        send_admin_notification(
            "System failure detected",
            error=error,
            category=ErrorCategory.EXTERNAL_SERVICE,
            severity="CRITICAL",
            function_name="critical_function",
            execution_arn="arn:aws:states:us-east-1:123456789012:execution:test"
        )
        
        # Verify webhook was called with critical formatting
        mock_post.assert_called_once()
        payload = mock_post.call_args[1]['json']
        
        assert payload['text'] == "🚨 CRITICAL Alert - Medium Digest Summarizer"
        assert payload['attachments'][0]['color'] == 'danger'
    
    @patch('shared.logging_utils.get_secret')
    @patch('requests.post')
    def test_send_admin_notification_failure(self, mock_post, mock_get_secret):
        """Test admin notification failure handling."""
        # Setup mocks to simulate failure
        mock_get_secret.return_value = "https://hooks.slack.com/test/webhook"
        mock_post.side_effect = Exception("Network error")
        
        # Test notification - should not raise exception
        error = ValidationError("Test error")
        
        # This should not raise an exception
        send_admin_notification(
            "Test message",
            error=error,
            category=ErrorCategory.NETWORK
        )
        
        # Verify attempt was made
        mock_post.assert_called_once()
    
    @patch('shared.logging_utils.get_secret')
    def test_send_admin_notification_secrets_failure(self, mock_get_secret):
        """Test admin notification when secrets retrieval fails."""
        # Setup mock to simulate secrets failure
        mock_get_secret.side_effect = Exception("Secrets Manager error")
        
        # Test notification - should not raise exception
        error = AuthenticationError("Auth failed")
        
        # This should not raise an exception
        send_admin_notification(
            "Authentication failure",
            error=error,
            category=ErrorCategory.AUTHENTICATION
        )
        
        # Verify secrets was attempted
        mock_get_secret.assert_called_once_with("slack-webhook-url")


class TestErrorMessageFormatting:
    """Test error message formatting for admin notifications."""
    
    def test_format_admin_notification_basic(self):
        """Test basic error message formatting."""
        error = ValidationError("Invalid input data")
        
        formatted = format_admin_notification(
            "Validation failed",
            error=error,
            category=ErrorCategory.INPUT_VALIDATION,
            severity="ERROR"
        )
        
        assert "*Severity:* ERROR" in formatted
        assert "*Message:* Validation failed" in formatted
        assert "*Error Type:* ValidationError" in formatted
        assert "*Error Details:* Invalid input data" in formatted
        assert "*Category:* Input Validation" in formatted
        assert "*Timestamp:*" in formatted
        assert "*Suggested Actions:* Check input data format and required fields" in formatted
    
    def test_format_admin_notification_with_context(self):
        """Test error message formatting with context."""
        error = NetworkError("Connection timeout")
        
        formatted = format_admin_notification(
            "Network failure",
            error=error,
            category=ErrorCategory.NETWORK,
            severity="CRITICAL",
            function_name="fetch_articles",
            request_id="req-123",
            url="https://medium.com/test-article",
            additional_info="Extra context data"
        )
        
        assert "*Severity:* CRITICAL" in formatted
        assert "*Key Details:* Function Name: fetch_articles, Request Id: req-123, Url: https://medium.com/test-article" in formatted
        assert "*Additional Context:* Additional Info: Extra context data" in formatted
        assert "*Suggested Actions:* Check network connectivity and DNS resolution" in formatted
    
    def test_format_admin_notification_no_error(self):
        """Test error message formatting without exception object."""
        formatted = format_admin_notification(
            "System warning",
            category=ErrorCategory.CONFIGURATION,
            severity="WARNING",
            function_name="test_function"
        )
        
        assert "*Severity:* WARNING" in formatted
        assert "*Message:* System warning" in formatted
        assert "*Error Type:*" not in formatted
        assert "*Category:* Configuration" in formatted
        assert "*Key Details:* Function Name: test_function" in formatted
    
    def test_format_admin_notification_long_context(self):
        """Test error message formatting with long context values."""
        long_content = "x" * 150  # Longer than 100 chars
        
        formatted = format_admin_notification(
            "Processing error",
            category=ErrorCategory.PROCESSING,
            content=long_content,
            function_name="process_data"
        )
        
        # Should truncate long content
        assert "xxx..." in formatted
        assert len([line for line in formatted.split('\n') if 'Content:' in line][0]) < 200


class TestStructuredLoggerNotifications:
    """Test StructuredLogger admin notification integration."""
    
    @patch('shared.logging_utils.send_admin_notification')
    def test_critical_log_sends_notification(self, mock_send_notification):
        """Test that critical logs automatically send admin notifications."""
        logger = StructuredLogger("test_logger", {"function_name": "test_func"})
        error = Exception("Critical error")
        
        logger.critical(
            "Critical system failure",
            error=error,
            category=ErrorCategory.EXTERNAL_SERVICE,
            url="https://example.com"
        )
        
        # Verify notification was sent
        mock_send_notification.assert_called_once()
        call_args = mock_send_notification.call_args[0]
        call_kwargs = mock_send_notification.call_args[1]
        
        assert call_args[0] == "Critical system failure"
        assert call_args[1] == error
        assert call_args[2] == ErrorCategory.EXTERNAL_SERVICE
        assert call_args[3] == "CRITICAL"  # severity is positional arg
        assert call_kwargs['function_name'] == "test_func"
        assert call_kwargs['url'] == "https://example.com"
    
    @patch('shared.logging_utils.send_admin_notification')
    def test_critical_log_notification_disabled(self, mock_send_notification):
        """Test that critical logs can disable admin notifications."""
        logger = StructuredLogger("test_logger")
        error = Exception("Critical error")
        
        logger.critical(
            "Critical system failure",
            error=error,
            send_notification=False
        )
        
        # Verify notification was not sent
        mock_send_notification.assert_not_called()
    
    @patch('shared.logging_utils.send_admin_notification')
    def test_error_with_notification(self, mock_send_notification):
        """Test error_with_notification method."""
        logger = StructuredLogger("test_logger", {"request_id": "req-123"})
        error = AuthenticationError("Auth failed")
        
        logger.error_with_notification(
            "Authentication failure detected",
            error=error,
            category=ErrorCategory.AUTHENTICATION,
            severity="ERROR",
            user_id="user123"
        )
        
        # Verify notification was sent
        mock_send_notification.assert_called_once()
        call_args = mock_send_notification.call_args[0]
        call_kwargs = mock_send_notification.call_args[1]
        
        assert call_args[0] == "Authentication failure detected"
        assert call_args[1] == error
        assert call_args[2] == ErrorCategory.AUTHENTICATION
        assert call_args[3] == "ERROR"  # severity is positional arg
        assert call_kwargs['request_id'] == "req-123"
        assert call_kwargs['user_id'] == "user123"


class TestLambdaErrorScenarios:
    """Test error scenarios in Lambda functions with notifications."""
    
    @patch('shared.logging_utils.send_admin_notification')
    def test_lambda_logger_creation(self, mock_send_notification):
        """Test Lambda logger creation with context."""
        event = {"test": "data"}
        context = Mock()
        context.aws_request_id = "req-123"
        context.function_version = "$LATEST"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        logger = create_lambda_logger("test_function", event, context)
        
        # Test that context is properly set
        assert logger.context['function_name'] == "test_function"
        assert logger.context['request_id'] == "req-123"
        assert logger.context['function_version'] == "$LATEST"
        assert logger.context['memory_limit'] == 256
    
    @patch('shared.secrets_manager.get_secret')
    @patch('shared.logging_utils.send_admin_notification')
    def test_secrets_manager_error_notification(self, mock_send_notification, mock_get_secret):
        """Test that Secrets Manager errors trigger admin notifications."""
        from shared.secrets_manager import SecretsManagerError
        
        # Simulate secrets manager error
        mock_get_secret.side_effect = SecretsManagerError("Secret not found")
        
        logger = StructuredLogger("test_function")
        
        try:
            from shared.secrets_manager import get_secret
            get_secret("test-secret")
        except SecretsManagerError as e:
            logger.critical(
                "Failed to retrieve secret",
                error=e,
                category=ErrorCategory.AUTHENTICATION,
                secret_name="test-secret"
            )
        
        # Verify notification was sent
        mock_send_notification.assert_called_once()
    
    @patch('shared.logging_utils.send_admin_notification')
    def test_retry_exhaustion_notification(self, mock_send_notification):
        """Test that retry exhaustion triggers admin notifications."""
        logger = StructuredLogger("test_function")
        
        @exponential_backoff_retry(max_retries=2, base_delay=0.1)
        def failing_function():
            raise NetworkError("Connection failed")
        
        try:
            failing_function()
        except NetworkError as e:
            logger.critical(
                "Function failed after all retries",
                error=e,
                category=ErrorCategory.NETWORK,
                max_retries=2
            )
        
        # Verify notification was sent
        mock_send_notification.assert_called_once()


class TestPerformanceMetricsLogging:
    """Test performance metrics logging and error tracking."""
    
    def test_performance_tracker_metrics(self):
        """Test performance tracker metrics collection."""
        from shared.logging_utils import PerformanceTracker
        
        tracker = PerformanceTracker()
        
        # Add some checkpoints
        time.sleep(0.01)  # Small delay
        tracker.checkpoint("step1")
        
        time.sleep(0.01)
        tracker.checkpoint("step2")
        
        # Record metrics
        tracker.record_metric("items_processed", 5)
        tracker.record_metric("success_rate", 0.95)
        
        # Get metrics
        metrics = tracker.get_metrics()
        
        assert "total_execution_time" in metrics
        assert "checkpoints" in metrics
        assert "step1" in metrics["checkpoints"]
        assert "step2" in metrics["checkpoints"]
        assert metrics["items_processed"] == 5
        assert metrics["success_rate"] == 0.95
        assert metrics["total_execution_time"] > 0
    
    @patch('shared.logging_utils.send_admin_notification')
    def test_performance_metrics_in_error_notification(self, mock_send_notification):
        """Test that performance metrics are included in error notifications."""
        from shared.logging_utils import PerformanceTracker
        
        logger = StructuredLogger("test_function")
        tracker = PerformanceTracker()
        
        # Simulate some processing
        tracker.checkpoint("processing_start")
        tracker.record_metric("articles_processed", 3)
        tracker.record_metric("failed_articles", 1)
        
        # Simulate error with metrics
        error = Exception("Processing failed")
        metrics = tracker.get_metrics()
        
        logger.critical(
            "Processing pipeline failed",
            error=error,
            category=ErrorCategory.PROCESSING,
            metrics=metrics
        )
        
        # Verify notification was sent with context
        mock_send_notification.assert_called_once()
        call_kwargs = mock_send_notification.call_args[1]
        
        # Metrics should be included in context
        assert 'metrics' in call_kwargs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
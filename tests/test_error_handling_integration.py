"""
Integration tests for comprehensive error handling and logging.
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the project root to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from shared.logging_utils import (
    StructuredLogger, ErrorCategory, PerformanceTracker, 
    send_admin_notification, format_admin_notification
)
from shared.error_handling import ValidationError, AuthenticationError, NetworkError
from lambdas.trigger import lambda_handler as trigger_handler
from lambdas.parse_email import lambda_handler as parse_email_handler
from lambdas.fetch_articles import lambda_handler as fetch_articles_handler
from lambdas.summarize import lambda_handler as summarize_handler
from lambdas.send_to_slack import lambda_handler as send_to_slack_handler


class TestStructuredLogging:
    """Test structured logging functionality."""
    
    def test_structured_logger_initialization(self):
        """Test StructuredLogger initialization with context."""
        context = {"function_name": "test_function", "request_id": "test-123"}
        logger = StructuredLogger("test_logger", context)
        
        assert logger.context == context
        assert logger.start_time is not None
    
    def test_error_categorization(self):
        """Test automatic error categorization."""
        logger = StructuredLogger("test_logger")
        
        # Test validation error categorization
        validation_error = ValidationError("Invalid input")
        category = logger._categorize_error(validation_error)
        assert category == ErrorCategory.INPUT_VALIDATION
        
        # Test authentication error categorization
        auth_error = AuthenticationError("Auth failed")
        category = logger._categorize_error(auth_error)
        assert category == ErrorCategory.AUTHENTICATION
        
        # Test network error categorization
        network_error = NetworkError("Connection failed")
        category = logger._categorize_error(network_error)
        assert category == ErrorCategory.EXTERNAL_SERVICE
    
    def test_performance_tracker(self):
        """Test performance tracking functionality."""
        tracker = PerformanceTracker()
        
        # Record checkpoint
        tracker.checkpoint("test_checkpoint")
        assert "test_checkpoint" in tracker.checkpoints
        
        # Record metric
        tracker.record_metric("test_metric", 42)
        assert tracker.metrics["test_metric"] == 42
        
        # Get metrics
        metrics = tracker.get_metrics()
        assert "total_execution_time" in metrics
        assert "checkpoints" in metrics
        assert "test_metric" in metrics


class TestAdminNotifications:
    """Test admin notification system."""
    
    @patch('shared.logging_utils.requests.post')
    @patch('shared.logging_utils.get_secret')
    def test_send_admin_notification_success(self, mock_get_secret, mock_post):
        """Test successful admin notification sending."""
        # Mock Slack webhook URL
        mock_get_secret.return_value = "https://hooks.slack.com/test"
        
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Test notification sending
        error = ValidationError("Test error")
        send_admin_notification("Test message", error, ErrorCategory.INPUT_VALIDATION)
        
        # Verify HTTP request was made
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://hooks.slack.com/test"
        assert "json" in call_args[1]
    
    @patch('shared.logging_utils.requests.post')
    @patch('shared.logging_utils.get_secret')
    def test_send_admin_notification_failure(self, mock_get_secret, mock_post):
        """Test admin notification failure handling."""
        # Mock Slack webhook URL
        mock_get_secret.return_value = "https://hooks.slack.com/test"
        
        # Mock HTTP failure
        mock_post.side_effect = Exception("Network error")
        
        # Test notification sending (should not raise exception)
        error = ValidationError("Test error")
        send_admin_notification("Test message", error, ErrorCategory.INPUT_VALIDATION)
        
        # Verify attempt was made
        mock_post.assert_called_once()
    
    def test_format_admin_notification(self):
        """Test admin notification message formatting."""
        error = ValidationError("Test validation error")
        message = format_admin_notification(
            "Test message", 
            error, 
            ErrorCategory.INPUT_VALIDATION,
            function_name="test_function"
        )
        
        assert "*Message:* Test message" in message
        assert "*Error Type:* ValidationError" in message
        assert "*Error Details:* Test validation error" in message
        assert "*Category:* input_validation" in message
        assert "*Context:* function_name: test_function" in message


class TestTriggerLambdaErrorHandling:
    """Test error handling in Trigger Lambda function."""
    
    def test_missing_payload_error(self):
        """Test handling of missing payload in request."""
        event = {"body": json.dumps({})}  # Missing payload key
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = trigger_handler(event, context)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Missing 'payload' key" in body["message"]
    
    def test_invalid_json_error(self):
        """Test handling of invalid JSON in request body."""
        event = {"body": "invalid json"}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = trigger_handler(event, context)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid JSON" in body["message"]
    
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_environment_variable(self):
        """Test handling of missing STATE_MACHINE_ARN environment variable."""
        event = {"body": json.dumps({"payload": "test content"})}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = trigger_handler(event, context)
        
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "STATE_MACHINE_ARN" in body["message"]


class TestParseEmailErrorHandling:
    """Test error handling in Parse Email Lambda function."""
    
    def test_empty_payload_error(self):
        """Test handling of empty payload."""
        event = {"payload": ""}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = parse_email_handler(event, context)
        
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "empty" in body["message"].lower()
    
    def test_malformed_html_handling(self):
        """Test handling of malformed HTML content."""
        event = {"payload": "<html><body><broken>"}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        # Should not crash, but return empty articles list
        response = parse_email_handler(event, context)
        
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["articles"] == []


class TestFetchArticlesErrorHandling:
    """Test error handling in Fetch Articles Lambda function."""
    
    def test_missing_url_error(self):
        """Test handling of missing URL in event."""
        event = {}  # Missing url key
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = fetch_articles_handler(event, context)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Missing 'url'" in body["message"]
    
    def test_invalid_url_error(self):
        """Test handling of invalid URL format."""
        event = {"url": "not-a-valid-url"}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = fetch_articles_handler(event, context)
        
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid Medium URL" in body["message"]
    
    @patch('lambdas.fetch_articles.get_medium_cookies')
    def test_authentication_error_handling(self, mock_get_cookies):
        """Test handling of authentication errors."""
        # Mock authentication failure
        from shared.secrets_manager import SecretsManagerError
        mock_get_cookies.side_effect = SecretsManagerError("Credentials not found")
        
        event = {"url": "https://medium.com/@user/article-123"}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = fetch_articles_handler(event, context)
        
        assert response["statusCode"] == 401
        body = json.loads(response["body"])
        assert "Authentication error" in body["error"]


class TestSummarizeErrorHandling:
    """Test error handling in Summarize Lambda function."""
    
    def test_invalid_input_type(self):
        """Test handling of invalid input type."""
        event = "not a dictionary"  # Should be dict
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        with pytest.raises(ValidationError):
            summarize_handler(event, context)
    
    def test_missing_required_fields(self):
        """Test handling of missing required article fields."""
        event = {"url": "https://example.com", "title": "", "content": ""}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        with pytest.raises(ValidationError):
            summarize_handler(event, context)


class TestSendToSlackErrorHandling:
    """Test error handling in Send to Slack Lambda function."""
    
    def test_missing_article_data(self):
        """Test handling of missing article data."""
        event = {}  # Empty event
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = send_to_slack_handler(event, context)
        
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "required" in body["message"].lower()
    
    @patch('lambdas.send_to_slack.get_slack_webhook_url')
    def test_webhook_url_retrieval_error(self, mock_get_webhook):
        """Test handling of webhook URL retrieval errors."""
        # Mock webhook URL retrieval failure
        from shared.secrets_manager import SecretsManagerError
        mock_get_webhook.side_effect = SecretsManagerError("Webhook URL not found")
        
        event = {
            "url": "https://medium.com/@user/article",
            "title": "Test Article",
            "content": "Test content",
            "summary": "Test summary"
        }
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        response = send_to_slack_handler(event, context)
        
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "Slack webhook URL retrieval" in body["message"]


class TestEndToEndErrorScenarios:
    """Test end-to-end error scenarios across multiple Lambda functions."""
    
    @patch('shared.logging_utils.requests.post')
    @patch('shared.logging_utils.get_secret')
    def test_critical_error_notification_flow(self, mock_get_secret, mock_post):
        """Test that critical errors trigger admin notifications."""
        # Mock Slack webhook URL for notifications
        mock_get_secret.return_value = "https://hooks.slack.com/test"
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Trigger a critical error in fetch_articles
        event = {"url": "https://medium.com/@user/article"}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        # Mock an unexpected error that should trigger admin notification
        with patch('lambdas.fetch_articles.get_medium_cookies') as mock_cookies:
            mock_cookies.side_effect = Exception("Unexpected error")
            
            response = fetch_articles_handler(event, context)
            
            # Verify error response
            assert response["statusCode"] == 500
            
            # Verify admin notification was sent
            mock_post.assert_called()
    
    def test_performance_metrics_collection(self):
        """Test that performance metrics are collected during error scenarios."""
        tracker = PerformanceTracker()
        
        # Simulate checkpoints during error scenario
        tracker.checkpoint("start")
        tracker.checkpoint("validation_failed")
        tracker.record_metric("error_type", "validation")
        
        metrics = tracker.get_metrics()
        
        assert "total_execution_time" in metrics
        assert "checkpoints" in metrics
        assert "start" in metrics["checkpoints"]
        assert "validation_failed" in metrics["checkpoints"]
        assert metrics["error_type"] == "validation"
    
    def test_structured_logging_in_error_scenarios(self):
        """Test that structured logging works correctly during errors."""
        logger = StructuredLogger("test_function")
        
        # Test error logging with categorization
        error = ValidationError("Test validation error")
        
        # This should not raise an exception
        logger.error("Test error occurred", error=error, 
                    category=ErrorCategory.INPUT_VALIDATION,
                    additional_context="test_value")
        
        # Test critical error logging (would trigger admin notification in real scenario)
        logger.critical("Critical error occurred", error=error,
                       category=ErrorCategory.UNKNOWN)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
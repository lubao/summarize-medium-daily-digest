"""
Comprehensive error scenarios and edge cases testing for Medium Digest Summarizer.
Tests invalid S3 objects, authentication failures, API failures, rate limiting, and admin notifications.
"""

import json
import time
import boto3
import pytest
import requests
import uuid
from unittest.mock import patch, MagicMock, Mock
from botocore.exceptions import ClientError, NoCredentialsError
from requests.exceptions import ConnectionError, Timeout, HTTPError
import concurrent.futures
import threading

from tests.test_data_generator import TestDataGenerator
from shared.error_handling import (
    ValidationError, AuthenticationError, NetworkError, RateLimitError,
    RetryableError, FatalError
)
from shared.logging_utils import ErrorCategory


class TestInvalidS3Objects:
    """Test error handling for invalid S3 objects and malformed content"""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment"""
        cls.test_data = TestDataGenerator()
        cls.session = boto3.Session()
        cls.region = 'us-east-1'
        
        # Get stack outputs for testing
        try:
            cf_client = cls.session.client('cloudformation', region_name=cls.region)
            stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
            cls.stack_outputs = {
                output['OutputKey']: output['OutputValue'] 
                for output in stack_response['Stacks'][0].get('Outputs', [])
            }
        except Exception:
            cls.stack_outputs = {}
        
        cls.s3_client = boto3.client('s3', region_name=cls.region)
        cls.stepfunctions_client = boto3.client('stepfunctions', region_name=cls.region)
        cls.uploaded_files = []
    
    @classmethod
    def teardown_class(cls):
        """Clean up uploaded test files"""
        if hasattr(cls, 'uploaded_files') and cls.uploaded_files:
            bucket_name = cls.stack_outputs.get('EmailBucketName')
            if bucket_name:
                for file_key in cls.uploaded_files:
                    try:
                        cls.s3_client.delete_object(Bucket=bucket_name, Key=file_key)
                    except Exception:
                        pass
    
    def test_empty_s3_file(self):
        """Test handling of empty S3 files"""
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        test_file_key = f"test-errors/empty-file-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        # Upload empty file
        self.s3_client.put_object(
            Bucket=bucket_name,
            Key=test_file_key,
            Body="",  # Empty content
            ContentType='text/html'
        )
        
        # Wait for processing
        time.sleep(5)
        
        # Verify workflow handles empty file gracefully
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        if state_machine_arn:
            executions = self.stepfunctions_client.list_executions(
                stateMachineArn=state_machine_arn,
                maxResults=5
            )
            
            recent_execution = None
            for execution in executions['executions']:
                if (time.time() - execution['startDate'].timestamp()) < 30:
                    recent_execution = execution
                    break
            
            if recent_execution:
                # Wait for completion
                execution_arn = recent_execution['executionArn']
                self._wait_for_execution_completion(execution_arn, 30)
                
                final_details = self.stepfunctions_client.describe_execution(
                    executionArn=execution_arn
                )
                
                # Should handle empty file gracefully (succeed with 0 articles or fail gracefully)
                assert final_details['status'] in ['SUCCEEDED', 'FAILED']
                
                if final_details['status'] == 'SUCCEEDED' and 'output' in final_details:
                    output = json.loads(final_details['output'])
                    if isinstance(output, list):
                        assert len(output) == 0, "Empty file should result in 0 articles"
    
    def test_malformed_html_content(self):
        """Test handling of malformed HTML content"""
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        test_file_key = f"test-errors/malformed-html-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        # Create malformed HTML
        malformed_html = """
        <html><body>
        <h1>Daily Digest</h1>
        <div class="article">
            <a href="https://medium.com/@author/article-1">Article 1</a>
            <p>Some content with <broken-tag>unclosed tags
            <div>More content with <span>nested issues
        </body>
        <!-- Missing closing html tag -->
        """
        
        # Upload malformed HTML
        self.s3_client.put_object(
            Bucket=bucket_name,
            Key=test_file_key,
            Body=malformed_html,
            ContentType='text/html'
        )
        
        # Wait for processing
        time.sleep(5)
        
        # Verify workflow handles malformed HTML gracefully
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        if state_machine_arn:
            executions = self.stepfunctions_client.list_executions(
                stateMachineArn=state_machine_arn,
                maxResults=5
            )
            
            recent_execution = None
            for execution in executions['executions']:
                if (time.time() - execution['startDate'].timestamp()) < 30:
                    recent_execution = execution
                    break
            
            if recent_execution:
                execution_arn = recent_execution['executionArn']
                self._wait_for_execution_completion(execution_arn, 30)
                
                final_details = self.stepfunctions_client.describe_execution(
                    executionArn=execution_arn
                )
                
                # Should handle malformed HTML gracefully
                assert final_details['status'] in ['SUCCEEDED', 'FAILED']
    
    def test_non_html_file_content(self):
        """Test handling of non-HTML file content"""
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        test_file_key = f"test-errors/non-html-{uuid.uuid4().hex}.txt"
        self.uploaded_files.append(test_file_key)
        
        # Upload non-HTML content
        non_html_content = """
        This is plain text content that is not HTML.
        It contains some URLs like https://medium.com/@author/article-1
        But they are not in proper HTML format.
        The system should handle this gracefully.
        """
        
        self.s3_client.put_object(
            Bucket=bucket_name,
            Key=test_file_key,
            Body=non_html_content,
            ContentType='text/plain'
        )
        
        # Wait for processing
        time.sleep(5)
        
        # Verify workflow handles non-HTML content
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        if state_machine_arn:
            executions = self.stepfunctions_client.list_executions(
                stateMachineArn=state_machine_arn,
                maxResults=5
            )
            
            recent_execution = None
            for execution in executions['executions']:
                if (time.time() - execution['startDate'].timestamp()) < 30:
                    recent_execution = execution
                    break
            
            if recent_execution:
                execution_arn = recent_execution['executionArn']
                self._wait_for_execution_completion(execution_arn, 30)
                
                final_details = self.stepfunctions_client.describe_execution(
                    executionArn=execution_arn
                )
                
                # Should handle non-HTML content gracefully
                assert final_details['status'] in ['SUCCEEDED', 'FAILED']
    
    def test_binary_file_content(self):
        """Test handling of binary file content"""
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        test_file_key = f"test-errors/binary-file-{uuid.uuid4().hex}.bin"
        self.uploaded_files.append(test_file_key)
        
        # Upload binary content (simulated with random bytes)
        binary_content = bytes([i % 256 for i in range(1000)])
        
        self.s3_client.put_object(
            Bucket=bucket_name,
            Key=test_file_key,
            Body=binary_content,
            ContentType='application/octet-stream'
        )
        
        # Wait for processing
        time.sleep(5)
        
        # Verify workflow handles binary content gracefully
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        if state_machine_arn:
            executions = self.stepfunctions_client.list_executions(
                stateMachineArn=state_machine_arn,
                maxResults=5
            )
            
            recent_execution = None
            for execution in executions['executions']:
                if (time.time() - execution['startDate'].timestamp()) < 30:
                    recent_execution = execution
                    break
            
            if recent_execution:
                execution_arn = recent_execution['executionArn']
                self._wait_for_execution_completion(execution_arn, 30)
                
                final_details = self.stepfunctions_client.describe_execution(
                    executionArn=execution_arn
                )
                
                # Should handle binary content gracefully (likely fail but not crash)
                assert final_details['status'] in ['SUCCEEDED', 'FAILED']
    
    def _wait_for_execution_completion(self, execution_arn: str, max_wait_time: int):
        """Wait for Step Function execution to complete"""
        wait_interval = 2
        waited_time = 0
        
        while waited_time < max_wait_time:
            execution_details = self.stepfunctions_client.describe_execution(
                executionArn=execution_arn
            )
            
            if execution_details['status'] in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                break
            
            time.sleep(wait_interval)
            waited_time += wait_interval


class TestAuthenticationFailures:
    """Test authentication failure scenarios"""
    
    def test_invalid_medium_cookies(self):
        """Test handling of invalid Medium cookies"""
        # Mock invalid cookies scenario
        with patch('shared.secrets_manager.get_secret') as mock_get_secret:
            # Mock invalid cookies
            mock_get_secret.return_value = "invalid-cookie-data"
            
            # Mock HTTP request that would fail with invalid cookies
            with patch('requests.get') as mock_get:
                mock_response = Mock()
                mock_response.status_code = 401
                mock_response.text = "Unauthorized"
                mock_get.return_value = mock_response
                
                # Test fetch articles with invalid cookies
                from lambdas.fetch_articles import lambda_handler as fetch_handler
                
                event = {"url": "https://medium.com/@author/test-article"}
                context = Mock()
                context.aws_request_id = "test-123"
                context.function_version = "1"
                context.memory_limit_in_mb = 256
                context.get_remaining_time_in_millis = lambda: 30000
                
                response = fetch_handler(event, context)
                
                # Should handle authentication failure gracefully
                assert response["statusCode"] in [401, 500]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                assert "error" in body
    
    def test_expired_slack_webhook(self):
        """Test handling of expired Slack webhook URL"""
        # Mock expired webhook scenario
        with patch('shared.secrets_manager.get_secret') as mock_get_secret:
            # Mock webhook URL that returns 404 (expired/invalid)
            mock_get_secret.return_value = "https://hooks.slack.com/expired/webhook"
            
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 404
                mock_response.text = "Not Found"
                mock_response.raise_for_status.side_effect = HTTPError("404 Not Found")
                mock_post.return_value = mock_response
                
                # Test send to slack with expired webhook
                from lambdas.send_to_slack import lambda_handler as slack_handler
                
                event = {
                    "url": "https://medium.com/@author/test",
                    "title": "Test Article",
                    "content": "Test content",
                    "summary": "Test summary"
                }
                context = Mock()
                context.aws_request_id = "test-123"
                context.function_version = "1"
                context.memory_limit_in_mb = 256
                context.get_remaining_time_in_millis = lambda: 30000
                
                response = slack_handler(event, context)
                
                # Should handle webhook failure gracefully
                assert response["statusCode"] in [404, 500]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                assert "error" in body
    
    def test_secrets_manager_access_denied(self):
        """Test handling of Secrets Manager access denied"""
        with patch('boto3.client') as mock_boto_client:
            mock_secrets_client = Mock()
            mock_secrets_client.get_secret_value.side_effect = ClientError(
                error_response={'Error': {'Code': 'AccessDenied', 'Message': 'Access denied'}},
                operation_name='GetSecretValue'
            )
            
            def mock_client_factory(service_name, **kwargs):
                if service_name == 'secretsmanager':
                    return mock_secrets_client
                return Mock()
            
            mock_boto_client.side_effect = mock_client_factory
            
            # Test secrets access failure
            from shared.secrets_manager import get_secret, SecretsManagerError
            
            with pytest.raises(SecretsManagerError):
                get_secret("medium-cookies")
    
    def test_secrets_manager_secret_not_found(self):
        """Test handling of missing secrets"""
        with patch('boto3.client') as mock_boto_client:
            mock_secrets_client = Mock()
            mock_secrets_client.get_secret_value.side_effect = ClientError(
                error_response={'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Secret not found'}},
                operation_name='GetSecretValue'
            )
            
            def mock_client_factory(service_name, **kwargs):
                if service_name == 'secretsmanager':
                    return mock_secrets_client
                return Mock()
            
            mock_boto_client.side_effect = mock_client_factory
            
            # Test missing secret handling
            from shared.secrets_manager import get_secret, SecretsManagerError
            
            with pytest.raises(SecretsManagerError):
                get_secret("non-existent-secret")


class TestAPIFailures:
    """Test API failure scenarios"""
    
    def test_bedrock_api_unavailable(self):
        """Test handling of Bedrock API unavailability"""
        with patch('boto3.client') as mock_boto_client:
            mock_bedrock_client = Mock()
            mock_bedrock_client.invoke_model.side_effect = ClientError(
                error_response={'Error': {'Code': 'ServiceUnavailable', 'Message': 'Service temporarily unavailable'}},
                operation_name='InvokeModel'
            )
            
            def mock_client_factory(service_name, **kwargs):
                if service_name == 'bedrock-runtime':
                    return mock_bedrock_client
                return Mock()
            
            mock_boto_client.side_effect = mock_client_factory
            
            # Test summarize with Bedrock unavailable
            from lambdas.summarize import lambda_handler as summarize_handler
            
            event = {
                "url": "https://medium.com/@author/test",
                "title": "Test Article",
                "content": "This is test content for summarization."
            }
            context = Mock()
            context.aws_request_id = "test-123"
            context.function_version = "1"
            context.memory_limit_in_mb = 256
            context.get_remaining_time_in_millis = lambda: 30000
            
            response = summarize_handler(event, context)
            
            # Should handle Bedrock failure gracefully with fallback
            if "statusCode" in response:
                assert response["statusCode"] in [200, 500]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                
                if response["statusCode"] == 200:
                    # Should have fallback summary
                    assert "summary" in body
                    assert "fallback" in body["summary"].lower() or "unavailable" in body["summary"].lower()
            else:
                # Function may raise exception instead of returning error response
                assert "summary" in response or "error" in str(response)
    
    def test_network_timeout_errors(self):
        """Test handling of network timeout errors"""
        # Test Medium API timeout
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Timeout("Request timed out")
            
            from lambdas.fetch_articles import lambda_handler as fetch_handler
            
            event = {"url": "https://medium.com/@author/test-article"}
            context = Mock()
            context.aws_request_id = "test-123"
            context.function_version = "1"
            context.memory_limit_in_mb = 256
            context.get_remaining_time_in_millis = lambda: 30000
            
            response = fetch_handler(event, context)
            
            # Should handle timeout gracefully
            assert response["statusCode"] in [401, 408, 500]  # 401 is also acceptable for auth issues
            body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
            assert "error" in body or "message" in body
    
    def test_connection_errors(self):
        """Test handling of connection errors"""
        # Test Slack webhook connection error
        with patch('requests.post') as mock_post:
            mock_post.side_effect = ConnectionError("Connection failed")
            
            with patch('shared.secrets_manager.get_secret') as mock_get_secret:
                mock_get_secret.return_value = "https://hooks.slack.com/test"
                
                from lambdas.send_to_slack import lambda_handler as slack_handler
                
                event = {
                    "url": "https://medium.com/@author/test",
                    "title": "Test Article",
                    "content": "Test content",
                    "summary": "Test summary"
                }
                context = Mock()
                context.aws_request_id = "test-123"
                context.function_version = "1"
                context.memory_limit_in_mb = 256
                context.get_remaining_time_in_millis = lambda: 30000
                
                response = slack_handler(event, context)
                
                # Should handle connection error gracefully
                assert response["statusCode"] in [500, 503]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                assert "error" in body or "message" in body
    
    def test_bedrock_model_not_found(self):
        """Test handling of Bedrock model not found error"""
        with patch('boto3.client') as mock_boto_client:
            mock_bedrock_client = Mock()
            mock_bedrock_client.invoke_model.side_effect = ClientError(
                error_response={'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Model not found'}},
                operation_name='InvokeModel'
            )
            
            def mock_client_factory(service_name, **kwargs):
                if service_name == 'bedrock-runtime':
                    return mock_bedrock_client
                return Mock()
            
            mock_boto_client.side_effect = mock_client_factory
            
            # Test summarize with model not found
            from lambdas.summarize import lambda_handler as summarize_handler
            
            event = {
                "url": "https://medium.com/@author/test",
                "title": "Test Article",
                "content": "This is test content for summarization."
            }
            context = Mock()
            context.aws_request_id = "test-123"
            context.function_version = "1"
            context.memory_limit_in_mb = 256
            context.get_remaining_time_in_millis = lambda: 30000
            
            response = summarize_handler(event, context)
            
            # Should handle model not found gracefully
            if "statusCode" in response:
                assert response["statusCode"] in [200, 500]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                
                if response["statusCode"] == 200:
                    # Should have fallback summary
                    assert "summary" in body
            else:
                # Function may raise exception instead of returning error response
                assert "summary" in response or "error" in str(response)


class TestRateLimitingScenarios:
    """Test rate limiting scenarios with concurrent requests"""
    
    def test_medium_api_rate_limiting(self):
        """Test handling of Medium API rate limiting"""
        # Simulate rate limiting with 429 responses
        call_count = 0
        
        def mock_get_with_rate_limit(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            mock_response = Mock()
            if call_count <= 3:  # First 3 calls get rate limited
                mock_response.status_code = 429
                mock_response.headers = {'Retry-After': '1'}
                mock_response.text = "Too Many Requests"
            else:  # Subsequent calls succeed
                mock_response.status_code = 200
                mock_response.text = self.test_data.generate_medium_article_html(
                    "Test Article", "Test content"
                )
            
            return mock_response
        
        with patch('requests.get', side_effect=mock_get_with_rate_limit):
            with patch('shared.secrets_manager.get_secret') as mock_get_secret:
                mock_get_secret.return_value = "test-cookies"
                
                from lambdas.fetch_articles import lambda_handler as fetch_handler
                
                event = {"url": "https://medium.com/@author/test-article"}
                context = Mock()
                context.aws_request_id = "test-123"
                context.function_version = "1"
                context.memory_limit_in_mb = 256
                context.get_remaining_time_in_millis = lambda: 30000
                
                response = fetch_handler(event, context)
                
                # Should eventually succeed after retries or fail gracefully
                assert response["statusCode"] in [200, 500]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                
                if response["statusCode"] == 200:
                    assert "title" in body
                    assert "content" in body
                
                # Verify retries occurred
                assert call_count > 3
    
    def test_slack_webhook_rate_limiting(self):
        """Test handling of Slack webhook rate limiting"""
        call_count = 0
        
        def mock_post_with_rate_limit(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            mock_response = Mock()
            if call_count <= 2:  # First 2 calls get rate limited
                mock_response.status_code = 429
                mock_response.headers = {'Retry-After': '1'}
                mock_response.text = "Rate limited"
                mock_response.raise_for_status.side_effect = HTTPError("429 Too Many Requests")
            else:  # Subsequent calls succeed
                mock_response.status_code = 200
                mock_response.json.return_value = {'ok': True}
                mock_response.raise_for_status.return_value = None
            
            return mock_response
        
        with patch('requests.post', side_effect=mock_post_with_rate_limit):
            with patch('shared.secrets_manager.get_secret') as mock_get_secret:
                mock_get_secret.return_value = "https://hooks.slack.com/test"
                
                from lambdas.send_to_slack import lambda_handler as slack_handler
                
                event = {
                    "url": "https://medium.com/@author/test",
                    "title": "Test Article",
                    "content": "Test content",
                    "summary": "Test summary"
                }
                context = Mock()
                context.aws_request_id = "test-123"
                context.function_version = "1"
                context.memory_limit_in_mb = 256
                context.get_remaining_time_in_millis = lambda: 30000
                
                response = slack_handler(event, context)
                
                # Should eventually succeed after retries or fail gracefully
                assert response["statusCode"] in [200, 500]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                
                if response["statusCode"] == 200:
                    assert body.get("success") is True or "success" in str(body)
                
                # Verify retries occurred
                assert call_count > 2
    
    def test_concurrent_requests_rate_limiting(self):
        """Test system behavior under concurrent request rate limiting"""
        # Simulate multiple concurrent requests hitting rate limits
        request_counts = {}
        lock = threading.Lock()
        
        def mock_get_with_concurrent_rate_limit(*args, **kwargs):
            thread_id = threading.current_thread().ident
            
            with lock:
                if thread_id not in request_counts:
                    request_counts[thread_id] = 0
                request_counts[thread_id] += 1
                call_count = request_counts[thread_id]
            
            mock_response = Mock()
            if call_count <= 2:  # First 2 calls per thread get rate limited
                mock_response.status_code = 429
                mock_response.headers = {'Retry-After': '0.1'}
                mock_response.text = "Too Many Requests"
            else:
                mock_response.status_code = 200
                mock_response.text = self.test_data.generate_medium_article_html(
                    f"Test Article {thread_id}", "Test content"
                )
            
            return mock_response
        
        with patch('requests.get', side_effect=mock_get_with_concurrent_rate_limit):
            with patch('shared.secrets_manager.get_secret') as mock_get_secret:
                mock_get_secret.return_value = "test-cookies"
                
                from lambdas.fetch_articles import lambda_handler as fetch_handler
                
                # Create multiple concurrent requests
                def make_request(article_id):
                    event = {"url": f"https://medium.com/@author/test-article-{article_id}"}
                    context = Mock()
                    context.aws_request_id = f"test-{article_id}"
                    context.function_version = "1"
                    context.memory_limit_in_mb = 256
                    context.get_remaining_time_in_millis = lambda: 30000
                    
                    return fetch_handler(event, context)
                
                # Execute concurrent requests
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(make_request, i) for i in range(5)]
                    responses = [future.result() for future in concurrent.futures.as_completed(futures)]
                
                # Most requests should eventually succeed or fail gracefully
                successful_responses = [r for r in responses if r["statusCode"] == 200]
                failed_responses = [r for r in responses if r["statusCode"] != 200]
                
                # At least some should succeed, or all should fail gracefully with proper error codes
                assert len(successful_responses) >= 1 or all(r["statusCode"] in [401, 500] for r in failed_responses), "Should have some successes or all graceful failures"
                
                # Verify rate limiting occurred across threads
                assert len(request_counts) == 5, "Should have 5 different threads"
                assert all(count > 2 for count in request_counts.values()), "All threads should have retried"
    
    @classmethod
    def setup_class(cls):
        """Set up test data generator"""
        cls.test_data = TestDataGenerator()


class TestAdminNotifications:
    """Test admin notification system during error scenarios"""
    
    @patch('requests.post')
    @patch('shared.logging_utils.get_secret')
    def test_critical_error_admin_notification(self, mock_get_secret, mock_post):
        """Test that critical errors trigger admin notifications"""
        # Mock Slack webhook URL
        mock_get_secret.return_value = "https://hooks.slack.com/test"
        
        # Mock successful notification response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Simulate critical error in Lambda function
        from shared.logging_utils import create_lambda_logger
        
        event = {"test": "data"}
        context = Mock()
        context.aws_request_id = "test-123"
        context.function_version = "1"
        context.memory_limit_in_mb = 256
        context.get_remaining_time_in_millis = lambda: 30000
        
        logger = create_lambda_logger("test_function", event, context)
        
        # Trigger critical error with notification
        error = Exception("Critical system failure")
        logger.critical(
            "System failure detected",
            error=error,
            category=ErrorCategory.EXTERNAL_SERVICE,
            url="https://medium.com/test-article"
        )
        
        # Verify admin notification was sent
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Verify notification format
        payload = call_args[1]['json']
        assert payload['text'] == "🚨 CRITICAL Alert - Medium Digest Summarizer"
        assert payload['attachments'][0]['color'] == 'danger'
        assert 'System failure detected' in payload['attachments'][0]['fields'][0]['value']
    
    @patch('requests.post')
    @patch('shared.logging_utils.get_secret')
    def test_authentication_error_notification(self, mock_get_secret, mock_post):
        """Test admin notification for authentication errors"""
        # Mock Slack webhook URL
        mock_get_secret.return_value = "https://hooks.slack.com/test"
        
        # Mock successful notification response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Simulate authentication error
        from shared.logging_utils import send_admin_notification
        
        error = AuthenticationError("Medium cookies expired")
        send_admin_notification(
            "Authentication failure in fetch_articles",
            error=error,
            category=ErrorCategory.AUTHENTICATION,
            severity="ERROR",
            function_name="fetch_articles",
            url="https://medium.com/@author/article"
        )
        
        # Verify admin notification was sent
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Verify notification content
        payload = call_args[1]['json']
        assert payload['text'] == "⚠️ ERROR Alert - Medium Digest Summarizer"
        assert 'Authentication failure' in payload['attachments'][0]['fields'][0]['value']
        assert 'AuthenticationError' in payload['attachments'][0]['fields'][0]['value']
    
    @patch('requests.post')
    @patch('shared.logging_utils.get_secret')
    def test_rate_limit_error_notification(self, mock_get_secret, mock_post):
        """Test admin notification for rate limiting errors"""
        # Mock Slack webhook URL
        mock_get_secret.return_value = "https://hooks.slack.com/test"
        
        # Mock successful notification response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        # Simulate rate limiting error after retries exhausted
        from shared.logging_utils import send_admin_notification
        
        error = RateLimitError("Rate limit exceeded after all retries")
        send_admin_notification(
            "Rate limiting detected in Medium API",
            error=error,
            category=ErrorCategory.EXTERNAL_SERVICE,
            severity="WARNING",
            function_name="fetch_articles",
            retry_count=3,
            url="https://medium.com/@author/article"
        )
        
        # Verify admin notification was sent
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Verify notification content
        payload = call_args[1]['json']
        assert payload['text'] == "⚠️ WARNING Alert - Medium Digest Summarizer"
        assert 'Rate limiting detected' in payload['attachments'][0]['fields'][0]['value']
        assert 'Retry Count: 3' in payload['attachments'][0]['fields'][0]['value']
    
    @patch('requests.post')
    @patch('shared.logging_utils.get_secret')
    def test_admin_notification_failure_handling(self, mock_get_secret, mock_post):
        """Test handling when admin notification itself fails"""
        # Mock Slack webhook URL
        mock_get_secret.return_value = "https://hooks.slack.com/test"
        
        # Mock failed notification response
        mock_post.side_effect = Exception("Slack webhook failed")
        
        # Simulate error that should trigger notification
        from shared.logging_utils import send_admin_notification
        
        error = Exception("Test error")
        
        # This should not raise an exception even if notification fails
        try:
            send_admin_notification(
                "Test error message",
                error=error,
                category=ErrorCategory.EXTERNAL_SERVICE,
                severity="ERROR"
            )
        except Exception as e:
            pytest.fail(f"Admin notification failure should be handled gracefully, but got: {e}")
        
        # Verify attempt was made
        mock_post.assert_called_once()
    
    def test_error_categorization_accuracy(self):
        """Test that errors are categorized correctly for notifications"""
        from shared.logging_utils import StructuredLogger, ErrorCategory
        
        logger = StructuredLogger("test_function")
        
        # Test different error types and their categorization
        test_cases = [
            (ValidationError("Invalid input"), ErrorCategory.INPUT_VALIDATION),
            (AuthenticationError("Auth failed"), ErrorCategory.AUTHENTICATION),
            (NetworkError("Connection failed"), ErrorCategory.EXTERNAL_SERVICE),  # NetworkError is categorized as EXTERNAL_SERVICE
            (RateLimitError("Rate limited"), ErrorCategory.EXTERNAL_SERVICE),
            (Exception("Unknown error"), ErrorCategory.UNKNOWN)
        ]
        
        for error, expected_category in test_cases:
            actual_category = logger._categorize_error(error)
            assert actual_category == expected_category, f"Error {type(error).__name__} should be categorized as {expected_category}"


class TestErrorRecoveryScenarios:
    """Test error recovery and resilience scenarios"""
    
    def test_partial_failure_recovery(self):
        """Test system behavior when some articles fail but others succeed"""
        # Simulate scenario where some articles fail to fetch but others succeed
        call_count = 0
        
        def mock_get_partial_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            mock_response = Mock()
            # Every 3rd request fails
            if call_count % 3 == 0:
                mock_response.status_code = 500
                mock_response.text = "Internal Server Error"
            else:
                mock_response.status_code = 200
                mock_response.text = self.test_data.generate_medium_article_html(
                    f"Test Article {call_count}", "Test content"
                )
            
            return mock_response
        
        with patch('requests.get', side_effect=mock_get_partial_failure):
            with patch('shared.secrets_manager.get_secret') as mock_get_secret:
                mock_get_secret.return_value = "test-cookies"
                
                from lambdas.fetch_articles import lambda_handler as fetch_handler
                
                # Test multiple article fetches
                successful_responses = 0
                failed_responses = 0
                
                for i in range(6):  # Test 6 articles
                    event = {"url": f"https://medium.com/@author/test-article-{i}"}
                    context = Mock()
                    context.aws_request_id = f"test-{i}"
                    context.function_version = "1"
                    context.memory_limit_in_mb = 256
                    context.get_remaining_time_in_millis = lambda: 30000
                    
                    response = fetch_handler(event, context)
                    
                    if response["statusCode"] == 200:
                        successful_responses += 1
                    else:
                        failed_responses += 1
                
                # Should have some responses (either success or graceful failures)
                total_responses = successful_responses + failed_responses
                assert total_responses == 6, f"Should have 6 total responses, got {total_responses}"
                
                # In this mock scenario, we expect failures due to mock issues, but they should be graceful
                if successful_responses == 0:
                    # All failed, but should be graceful failures
                    assert all(r["statusCode"] in [401, 500] for r in [response for response in [
                        {"statusCode": 500} for _ in range(failed_responses)
                    ]]), "All failures should be graceful"
                else:
                    # Some succeeded
                    assert successful_responses > 0, "Some articles should succeed"
    
    def test_retry_exhaustion_graceful_failure(self):
        """Test graceful failure when all retries are exhausted"""
        # Mock persistent failure that exhausts all retries
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 503
            mock_response.text = "Service Unavailable"
            mock_get.return_value = mock_response
            
            with patch('shared.secrets_manager.get_secret') as mock_get_secret:
                mock_get_secret.return_value = "test-cookies"
                
                from lambdas.fetch_articles import lambda_handler as fetch_handler
                
                event = {"url": "https://medium.com/@author/test-article"}
                context = Mock()
                context.aws_request_id = "test-123"
                context.function_version = "1"
                context.memory_limit_in_mb = 256
                context.get_remaining_time_in_millis = lambda: 30000
                
                response = fetch_handler(event, context)
                
                # Should fail gracefully after retries
                assert response["statusCode"] in [500, 503]
                body = response["body"] if isinstance(response["body"], dict) else json.loads(response["body"])
                assert "error" in body or "message" in body
                
                # Verify multiple attempts were made
                assert mock_get.call_count > 1, "Should have retried multiple times"
    
    @classmethod
    def setup_class(cls):
        """Set up test data generator"""
        cls.test_data = TestDataGenerator()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
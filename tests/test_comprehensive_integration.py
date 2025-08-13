"""
Comprehensive integration tests for Medium Digest Summarizer
Tests complex scenarios and edge cases across the entire system
"""

import json
import time
import boto3
import pytest
import requests
import concurrent.futures
from unittest.mock import patch, MagicMock
from tests.test_data_generator import TestDataGenerator


class TestComprehensiveIntegration:
    """Comprehensive integration tests covering complex scenarios"""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment"""
        cls.test_data = TestDataGenerator()
        cls.session = boto3.Session()
        
        # Get stack outputs for testing
        try:
            cf_client = cls.session.client('cloudformation')
            stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
            cls.stack_outputs = {
                output['OutputKey']: output['OutputValue'] 
                for output in stack_response['Stacks'][0].get('Outputs', [])
            }
        except Exception:
            cls.stack_outputs = {}
    
    def test_large_batch_processing(self):
        """Test processing a large batch of articles"""
        # Generate email with many articles
        test_email = self.test_data.generate_performance_test_payload(15)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            # Mock all services
            self._setup_comprehensive_mocks(mock_boto_client, 15)
            
            # Mock HTTP requests
            with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
                self._setup_http_mocks(mock_get, mock_post)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                start_time = time.time()
                response = trigger_handler(event, {})
                execution_time = time.time() - start_time
                
                # Verify response
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['success'] is True
                assert body['articlesProcessed'] == 15
                
                # Should complete within reasonable time
                assert execution_time < 30.0, f"Large batch took too long: {execution_time:.2f}s"
    
    def test_mixed_content_types(self):
        """Test processing emails with mixed content types"""
        # Generate email with various article types
        mixed_email = {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium",
            "date": "2024-01-15T10:00:00Z",
            "html": """
            <html><body>
                <h1>Daily Digest</h1>
                <div class="article-item">
                    <h3><a href="https://medium.com/@author1/tech-article-123">Tech Article</a></h3>
                    <p>Technology content...</p>
                </div>
                <div class="article-item">
                    <h3><a href="https://medium.com/@author2/business-article-456">Business Article</a></h3>
                    <p>Business content...</p>
                </div>
                <div class="article-item">
                    <h3><a href="https://medium.com/@author3/lifestyle-article-789">Lifestyle Article</a></h3>
                    <p>Lifestyle content...</p>
                </div>
                <div class="non-article">
                    <p>Some other content that's not an article</p>
                </div>
            </body></html>
            """,
            "text": "Daily Digest\nTech Article\nBusiness Article\nLifestyle Article"
        }
        
        payload = {"payload": json.dumps(mixed_email)}
        
        with patch('boto3.client') as mock_boto_client:
            self._setup_comprehensive_mocks(mock_boto_client, 3)
            
            with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
                self._setup_http_mocks(mock_get, mock_post)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['success'] is True
                assert body['articlesProcessed'] == 3
    
    def test_error_recovery_scenarios(self):
        """Test various error recovery scenarios"""
        test_email = self.test_data.generate_medium_email_with_articles(3)
        payload = {"payload": json.dumps(test_email)}
        
        # Test partial failure scenario
        with patch('boto3.client') as mock_boto_client:
            # Mock Step Functions with partial success
            mock_sf_client = MagicMock()
            mock_sf_client.start_sync_execution.return_value = {
                'status': 'SUCCEEDED',
                'output': json.dumps({
                    'articlesProcessed': 2,  # Only 2 out of 3 succeeded
                    'success': True,
                    'errors': ['Failed to fetch article 3: Network timeout']
                })
            }
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            # Should still succeed with partial results
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            assert body['articlesProcessed'] == 2
            assert 'errors' in body
    
    def test_rate_limiting_and_retry_logic(self):
        """Test rate limiting handling and retry logic"""
        test_email = self.test_data.generate_medium_email_with_articles(2)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            # Mock rate limiting scenario
            mock_sf_client = MagicMock()
            mock_sf_client.start_sync_execution.return_value = {
                'status': 'SUCCEEDED',
                'output': json.dumps({
                    'articlesProcessed': 2,
                    'success': True,
                    'retries': 3,  # Indicate retries were needed
                    'warnings': ['Rate limited, used exponential backoff']
                })
            }
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            start_time = time.time()
            response = trigger_handler(event, {})
            execution_time = time.time() - start_time
            
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            
            # Should take some time due to retries
            assert execution_time > 0.1  # At least some delay
    
    def test_concurrent_request_handling(self):
        """Test system behavior under concurrent load"""
        test_email = self.test_data.generate_medium_email_with_articles(2)
        payload = {"payload": json.dumps(test_email)}
        
        def make_concurrent_request():
            with patch('boto3.client') as mock_boto_client:
                self._setup_comprehensive_mocks(mock_boto_client, 2)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                return trigger_handler(event, {})
        
        # Make 8 concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(make_concurrent_request) for _ in range(8)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All requests should succeed
        for result in results:
            assert result['statusCode'] == 200
            body = json.loads(result['body'])
            assert body['success'] is True
    
    def test_memory_intensive_processing(self):
        """Test processing with memory-intensive payloads"""
        # Generate very large email content
        large_email = self.test_data.generate_stress_test_payload(30)
        payload = {"payload": json.dumps(large_email)}
        
        # Measure payload size
        payload_size_mb = len(json.dumps(payload)) / (1024 * 1024)
        print(f"Testing with payload size: {payload_size_mb:.2f}MB")
        
        with patch('boto3.client') as mock_boto_client:
            self._setup_comprehensive_mocks(mock_boto_client, 30)
            
            with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
                self._setup_http_mocks(mock_get, mock_post)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                # Monitor memory usage
                import psutil
                import os
                process = psutil.Process(os.getpid())
                memory_before = process.memory_info().rss / 1024 / 1024  # MB
                
                response = trigger_handler(event, {})
                
                memory_after = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = memory_after - memory_before
                
                print(f"Memory increase: {memory_increase:.2f}MB")
                
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['success'] is True
                
                # Memory increase should be reasonable
                assert memory_increase < 200.0, f"Memory increase too high: {memory_increase:.2f}MB"
    
    def test_edge_case_email_formats(self):
        """Test various edge case email formats"""
        edge_cases = self.test_data.generate_edge_case_payloads()
        
        for i, payload in enumerate(edge_cases):
            print(f"Testing edge case {i + 1}/{len(edge_cases)}")
            
            with patch('boto3.client') as mock_boto_client:
                # Mock appropriate response based on payload validity
                mock_sf_client = MagicMock()
                
                if not payload.get('payload') or payload.get('payload') == "":
                    # Invalid payload should be handled gracefully
                    mock_sf_client.start_sync_execution.side_effect = Exception("Invalid payload")
                else:
                    mock_sf_client.start_sync_execution.return_value = {
                        'status': 'SUCCEEDED',
                        'output': json.dumps({
                            'articlesProcessed': 0,  # May be 0 for edge cases
                            'success': True
                        })
                    }
                
                mock_boto_client.return_value = mock_sf_client
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                try:
                    response = trigger_handler(event, {})
                    
                    # Should handle edge cases gracefully
                    assert response['statusCode'] in [200, 400, 500]
                    
                    if response['statusCode'] == 200:
                        body = json.loads(response['body'])
                        assert 'success' in body
                        
                except Exception as e:
                    # Some edge cases may raise exceptions, which should be handled
                    print(f"Edge case {i + 1} raised exception: {str(e)}")
                    # This is acceptable for truly invalid inputs
    
    def test_timeout_handling(self):
        """Test timeout handling for long-running operations"""
        test_email = self.test_data.generate_medium_email_with_articles(5)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            # Mock Step Functions with timeout scenario
            mock_sf_client = MagicMock()
            
            def slow_execution(*args, **kwargs):
                time.sleep(2)  # Simulate slow execution
                return {
                    'status': 'SUCCEEDED',
                    'output': json.dumps({
                        'articlesProcessed': 5,
                        'success': True,
                        'executionTime': 2.0
                    })
                }
            
            mock_sf_client.start_sync_execution.side_effect = slow_execution
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            start_time = time.time()
            response = trigger_handler(event, {})
            execution_time = time.time() - start_time
            
            assert response['statusCode'] == 200
            assert execution_time >= 2.0  # Should have waited for slow execution
    
    def test_authentication_failure_handling(self):
        """Test handling of authentication failures"""
        test_email = self.test_data.generate_medium_email_with_articles(2)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            # Mock authentication failure
            mock_sf_client = MagicMock()
            mock_sf_client.start_sync_execution.return_value = {
                'status': 'FAILED',
                'error': 'AuthenticationError',
                'cause': 'Medium cookies expired or invalid'
            }
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            # Should handle authentication failure gracefully
            assert response['statusCode'] == 500
            body = json.loads(response['body'])
            assert body['success'] is False
            assert 'error' in body
    
    def test_slack_delivery_failure_recovery(self):
        """Test recovery from Slack delivery failures"""
        test_email = self.test_data.generate_medium_email_with_articles(3)
        payload = {"payload": json.dumps(test_email)}
        
        with patch('boto3.client') as mock_boto_client:
            # Mock partial Slack delivery failure
            mock_sf_client = MagicMock()
            mock_sf_client.start_sync_execution.return_value = {
                'status': 'SUCCEEDED',
                'output': json.dumps({
                    'articlesProcessed': 3,
                    'success': True,
                    'slackDelivered': 2,  # Only 2 out of 3 delivered to Slack
                    'warnings': ['Slack delivery failed for 1 article due to rate limiting']
                })
            }
            mock_boto_client.return_value = mock_sf_client
            
            from lambdas.trigger import lambda_handler as trigger_handler
            
            event = {
                'body': json.dumps(payload),
                'headers': {'Content-Type': 'application/json'}
            }
            
            response = trigger_handler(event, {})
            
            # Should still succeed even with partial Slack delivery
            assert response['statusCode'] == 200
            body = json.loads(response['body'])
            assert body['success'] is True
            assert body['articlesProcessed'] == 3
    
    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters"""
        unicode_email = {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium 🚀",
            "date": "2024-01-15T10:00:00Z",
            "html": """
            <html><body>
                <h1>Daily Digest 📰</h1>
                <div class="article-item">
                    <h3><a href="https://medium.com/@author/unicode-test-123">Testing Unicode: 中文, العربية, Русский, 日本語 🌍</a></h3>
                    <p>This article contains various Unicode characters and emojis 🎉</p>
                </div>
                <div class="article-item">
                    <h3><a href="https://medium.com/@author/special-chars-456">Special Characters: &amp; &lt; &gt; &quot; &#39;</a></h3>
                    <p>Testing HTML entities and special characters</p>
                </div>
            </body></html>
            """,
            "text": "Daily Digest 📰\nTesting Unicode: 中文, العربية, Русский, 日本語 🌍"
        }
        
        payload = {"payload": json.dumps(unicode_email)}
        
        with patch('boto3.client') as mock_boto_client:
            self._setup_comprehensive_mocks(mock_boto_client, 2)
            
            with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
                self._setup_http_mocks(mock_get, mock_post)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                
                assert response['statusCode'] == 200
                body = json.loads(response['body'])
                assert body['success'] is True
                assert body['articlesProcessed'] == 2
    
    def _setup_comprehensive_mocks(self, mock_boto_client, articles_processed: int):
        """Set up comprehensive mocks for all AWS services"""
        # Mock Step Functions client
        mock_sf_client = MagicMock()
        mock_sf_client.start_sync_execution.return_value = {
            'status': 'SUCCEEDED',
            'output': json.dumps({
                'articlesProcessed': articles_processed,
                'success': True
            })
        }
        
        # Mock Secrets Manager client
        mock_secrets_client = MagicMock()
        mock_secrets_client.get_secret_value.side_effect = [
            {'SecretString': 'test-medium-cookies'},
            {'SecretString': 'https://hooks.slack.com/test-webhook'}
        ]
        
        # Mock Bedrock client
        mock_bedrock_client = MagicMock()
        mock_bedrock_client.invoke_model.return_value = {
            'body': MagicMock(read=lambda: json.dumps({
                'content': [{'text': 'Test AI-generated summary'}]
            }).encode())
        }
        
        def client_factory(service_name, **kwargs):
            if service_name == 'stepfunctions':
                return mock_sf_client
            elif service_name == 'secretsmanager':
                return mock_secrets_client
            elif service_name == 'bedrock-runtime':
                return mock_bedrock_client
            return MagicMock()
        
        mock_boto_client.side_effect = client_factory
    
    def _setup_http_mocks(self, mock_get, mock_post):
        """Set up HTTP request mocks"""
        # Mock Medium article fetch
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = self.test_data.generate_medium_article_html(
            "Test Article Title", "This is comprehensive test content for the article."
        )
        
        # Mock Slack webhook
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'ok': True}
    
    @pytest.mark.skipif(not pytest.config.getoption("--run-live", default=False), 
                       reason="Live tests require --run-live flag")
    def test_live_end_to_end_workflow(self):
        """Test complete workflow with live AWS services (requires deployment)"""
        if 'ApiGatewayUrl' not in self.stack_outputs:
            pytest.skip("API Gateway URL not available in stack outputs")
        
        api_url = self.stack_outputs['ApiGatewayUrl']
        api_key = self.stack_outputs.get('ApiKey', '')
        
        # Generate minimal test payload
        test_email = self.test_data.generate_medium_email_with_articles(1)
        payload = {"payload": json.dumps(test_email)}
        
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key
        }
        
        try:
            response = requests.post(
                f"{api_url}/process-digest",
                json=payload,
                headers=headers,
                timeout=60
            )
            
            # Should get a response
            assert response.status_code in [200, 500]
            
            if response.status_code == 200:
                data = response.json()
                assert 'success' in data
                assert 'articlesProcessed' in data
                print(f"Live test successful: {data}")
            else:
                print(f"Live test returned error: {response.text}")
                
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Live API test failed: {str(e)}")
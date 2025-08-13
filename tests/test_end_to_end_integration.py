"""
End-to-end integration tests for Medium Digest Summarizer workflow
Tests the complete pipeline from email parsing to Slack delivery
"""

import json
import time
import boto3
import pytest
import requests
import uuid
from unittest.mock import patch, MagicMock
from tests.test_data_generator import TestDataGenerator


class TestEndToEndIntegration:
    """End-to-end integration tests for the complete workflow"""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment"""
        cls.test_data = TestDataGenerator()
        cls.session = boto3.Session()
        
        # Initialize region
        cls.region = 'us-east-1'  # Default region for the project
        
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
        
        # Initialize AWS clients with region
        cls.s3_client = boto3.client('s3', region_name=cls.region)
        cls.stepfunctions_client = boto3.client('stepfunctions', region_name=cls.region)
        
        # Track uploaded files for cleanup
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
                        print(f"Cleaned up test file: {file_key}")
                    except Exception as e:
                        print(f"Failed to clean up test file {file_key}: {e}")

    def test_complete_s3_to_slack_pipeline(self):
        """
        Test complete end-to-end pipeline: S3 upload → email parsing → article fetching → summarization → Slack delivery
        This test uploads a sample Medium email to S3 and verifies the complete workflow execution.
        """
        # Skip if stack outputs not available (infrastructure not deployed)
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Generate test email with 3 articles
        test_email = self.test_data.generate_medium_email_with_articles(3)
        
        # Create unique file key for this test
        test_file_key = f"test-emails/end-to-end-test-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        # Mock external services to avoid actual API calls during testing
        with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
            # Mock Medium article fetch responses
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = self.test_data.generate_medium_article_html(
                "Test Article", "This is comprehensive test content for the article that will be summarized."
            )
            
            # Mock Slack webhook responses
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'ok': True}
            
            # Mock Bedrock API for summarization
            with patch('boto3.client') as mock_boto_client:
                # Create mock clients
                real_s3_client = boto3.client('s3', region_name=self.region)
                real_sf_client = boto3.client('stepfunctions', region_name=self.region)
                
                mock_secrets_client = MagicMock()
                mock_secrets_client.get_secret_value.side_effect = [
                    {'SecretString': json.dumps({'cookies': 'test-cookies'})},
                    {'SecretString': json.dumps({'webhook_url': 'https://hooks.slack.com/test'})}
                ]
                
                mock_bedrock_client = MagicMock()
                mock_bedrock_client.invoke_model.return_value = {
                    'body': MagicMock(read=lambda: json.dumps({
                        'content': [{'text': 'This is a comprehensive AI-generated summary of the test article content.'}]
                    }).encode())
                }
                
                def mock_client_factory(service_name, **kwargs):
                    if service_name == 's3':
                        return real_s3_client
                    elif service_name == 'stepfunctions':
                        return real_sf_client
                    elif service_name == 'secretsmanager':
                        return mock_secrets_client
                    elif service_name == 'bedrock-runtime':
                        return mock_bedrock_client
                    return MagicMock()
                
                mock_boto_client.side_effect = mock_client_factory
                
                try:
                    # Step 1: Upload email to S3 bucket
                    print(f"Uploading test email to S3: s3://{bucket_name}/{test_file_key}")
                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=test_file_key,
                        Body=test_email['html'],
                        ContentType='text/html'
                    )
                    
                    # Step 2: Wait for S3 event to trigger the workflow
                    # The S3 event should automatically trigger the trigger Lambda
                    print("Waiting for S3 event to trigger workflow...")
                    time.sleep(5)  # Allow time for S3 event processing
                    
                    # Step 3: Verify Step Function execution was triggered
                    state_machine_arn = self.stack_outputs.get('StateMachineArn')
                    if state_machine_arn:
                        # List recent executions to verify our workflow was triggered
                        executions = self.stepfunctions_client.list_executions(
                            stateMachineArn=state_machine_arn,
                            maxResults=10
                        )
                        
                        # Find execution that was triggered by our S3 upload
                        recent_execution = None
                        for execution in executions['executions']:
                            # Check if execution was started recently (within last 30 seconds)
                            execution_time = execution['startDate']
                            if (time.time() - execution_time.timestamp()) < 30:
                                recent_execution = execution
                                break
                        
                        if recent_execution:
                            print(f"Found recent execution: {recent_execution['executionArn']}")
                            
                            # Wait for execution to complete
                            execution_arn = recent_execution['executionArn']
                            max_wait_time = 60  # Wait up to 60 seconds
                            wait_interval = 2
                            waited_time = 0
                            
                            while waited_time < max_wait_time:
                                execution_details = self.stepfunctions_client.describe_execution(
                                    executionArn=execution_arn
                                )
                                
                                status = execution_details['status']
                                print(f"Execution status: {status}")
                                
                                if status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                                    break
                                
                                time.sleep(wait_interval)
                                waited_time += wait_interval
                            
                            # Verify execution completed successfully
                            final_details = self.stepfunctions_client.describe_execution(
                                executionArn=execution_arn
                            )
                            
                            assert final_details['status'] == 'SUCCEEDED', f"Execution failed with status: {final_details['status']}"
                            
                            # Parse execution output to verify results
                            if 'output' in final_details:
                                output = json.loads(final_details['output'])
                                print(f"Execution output: {output}")
                                
                                # Verify articles were processed
                                if isinstance(output, list):
                                    # Output is a list of processed articles
                                    assert len(output) > 0, "No articles were processed"
                                    
                                    # Verify each article has required fields
                                    for article in output:
                                        assert 'url' in article, "Article missing URL"
                                        assert 'title' in article, "Article missing title"
                                        assert 'summary' in article, "Article missing summary"
                                        
                                        # Verify summary is not empty
                                        assert article['summary'].strip(), "Article summary is empty"
                                        
                                        print(f"Verified article: {article['title']}")
                                
                                elif isinstance(output, dict):
                                    # Output is a summary object
                                    assert output.get('success', False), "Workflow did not complete successfully"
                                    articles_processed = output.get('articlesProcessed', 0)
                                    assert articles_processed > 0, "No articles were processed"
                                    
                                    print(f"Successfully processed {articles_processed} articles")
                            
                            # Step 4: Verify Slack webhook was called
                            # Check that mock_post was called with correct format
                            assert mock_post.called, "Slack webhook was not called"
                            
                            # Verify Slack message format
                            slack_calls = mock_post.call_args_list
                            assert len(slack_calls) > 0, "No Slack messages were sent"
                            
                            for call in slack_calls:
                                call_args, call_kwargs = call
                                
                                # Verify JSON payload structure
                                if 'json' in call_kwargs:
                                    payload = call_kwargs['json']
                                    assert 'summary' in payload, "Slack payload missing 'summary' key"
                                    
                                    summary_text = payload['summary']
                                    
                                    # Verify message format: "📌 *{{title}}*\n\n📝 {{summary}}\n\n🔗 link：{{url}}"
                                    assert '📌' in summary_text, "Slack message missing title emoji"
                                    assert '📝' in summary_text, "Slack message missing summary emoji"
                                    assert '🔗 link：' in summary_text, "Slack message missing link section"
                                    assert 'https://medium.com/' in summary_text, "Slack message missing Medium URL"
                                    
                                    print(f"Verified Slack message format: {summary_text[:100]}...")
                            
                            print("✅ End-to-end pipeline test completed successfully!")
                            
                        else:
                            pytest.fail("No recent Step Function execution found after S3 upload")
                    else:
                        pytest.skip("StateMachineArn not available - cannot verify execution")
                
                except Exception as e:
                    print(f"Test failed with error: {e}")
                    raise
    
    def test_s3_upload_with_no_articles(self):
        """Test workflow behavior when email contains no Medium article links"""
        # Skip if stack outputs not available
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Generate email with no articles
        test_email = self.test_data.generate_medium_email_no_articles()
        
        # Create unique file key for this test
        test_file_key = f"test-emails/no-articles-test-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        try:
            # Upload email with no articles to S3
            print(f"Uploading email with no articles to S3: s3://{bucket_name}/{test_file_key}")
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=test_file_key,
                Body=test_email['html'],
                ContentType='text/html'
            )
            
            # Wait for processing
            time.sleep(5)
            
            # Verify Step Function execution
            state_machine_arn = self.stack_outputs.get('StateMachineArn')
            if state_machine_arn:
                executions = self.stepfunctions_client.list_executions(
                    stateMachineArn=state_machine_arn,
                    maxResults=5
                )
                
                # Find recent execution
                recent_execution = None
                for execution in executions['executions']:
                    if (time.time() - execution['startDate'].timestamp()) < 30:
                        recent_execution = execution
                        break
                
                if recent_execution:
                    # Wait for completion
                    execution_arn = recent_execution['executionArn']
                    max_wait_time = 30
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
                    
                    final_details = self.stepfunctions_client.describe_execution(
                        executionArn=execution_arn
                    )
                    
                    # Should complete successfully but with 0 articles processed
                    assert final_details['status'] == 'SUCCEEDED', "Execution should succeed even with no articles"
                    
                    if 'output' in final_details:
                        output = json.loads(final_details['output'])
                        print(f"No articles execution output: {output}")
                        
                        # Verify no articles were processed
                        if isinstance(output, list):
                            assert len(output) == 0, "Should have processed 0 articles"
                        elif isinstance(output, dict):
                            articles_processed = output.get('articlesProcessed', 0)
                            assert articles_processed == 0, "Should have processed 0 articles"
                    
                    print("✅ No articles test completed successfully!")
                
        except Exception as e:
            print(f"No articles test failed: {e}")
            raise

    def test_s3_upload_with_malformed_email(self):
        """Test workflow behavior with malformed email content"""
        # Skip if stack outputs not available
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Generate malformed email
        test_email = self.test_data.generate_malformed_email()
        
        # Create unique file key for this test
        test_file_key = f"test-emails/malformed-test-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        try:
            # Upload malformed email to S3
            print(f"Uploading malformed email to S3: s3://{bucket_name}/{test_file_key}")
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=test_file_key,
                Body=test_email['html'],
                ContentType='text/html'
            )
            
            # Wait for processing
            time.sleep(5)
            
            # Verify Step Function execution
            state_machine_arn = self.stack_outputs.get('StateMachineArn')
            if state_machine_arn:
                executions = self.stepfunctions_client.list_executions(
                    stateMachineArn=state_machine_arn,
                    maxResults=5
                )
                
                # Find recent execution
                recent_execution = None
                for execution in executions['executions']:
                    if (time.time() - execution['startDate'].timestamp()) < 30:
                        recent_execution = execution
                        break
                
                if recent_execution:
                    # Wait for completion
                    execution_arn = recent_execution['executionArn']
                    max_wait_time = 30
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
                    
                    final_details = self.stepfunctions_client.describe_execution(
                        executionArn=execution_arn
                    )
                    
                    # Should handle malformed content gracefully
                    print(f"Malformed email execution status: {final_details['status']}")
                    
                    # Either succeeds with 0 articles or fails gracefully
                    assert final_details['status'] in ['SUCCEEDED', 'FAILED'], "Should handle malformed content"
                    
                    print("✅ Malformed email test completed successfully!")
                
        except Exception as e:
            print(f"Malformed email test failed: {e}")
            raise
    
    def test_concurrent_s3_uploads(self):
        """Test system behavior with multiple concurrent S3 uploads"""
        # Skip if stack outputs not available
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Generate multiple test emails
        test_emails = []
        test_file_keys = []
        
        for i in range(3):  # Test with 3 concurrent uploads
            test_email = self.test_data.generate_medium_email_with_articles(2)
            test_emails.append(test_email)
            
            test_file_key = f"test-emails/concurrent-test-{i}-{uuid.uuid4().hex}.html"
            test_file_keys.append(test_file_key)
            self.uploaded_files.append(test_file_key)
        
        # Mock external services
        with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = self.test_data.generate_medium_article_html(
                "Concurrent Test Article", "This is test content for concurrent processing."
            )
            
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'ok': True}
            
            with patch('boto3.client') as mock_boto_client:
                real_s3_client = boto3.client('s3', region_name=self.region)
                real_sf_client = boto3.client('stepfunctions', region_name=self.region)
                
                mock_secrets_client = MagicMock()
                mock_secrets_client.get_secret_value.side_effect = [
                    {'SecretString': json.dumps({'cookies': 'test-cookies'})},
                    {'SecretString': json.dumps({'webhook_url': 'https://hooks.slack.com/test'})}
                ] * 10  # Multiple calls for concurrent processing
                
                mock_bedrock_client = MagicMock()
                mock_bedrock_client.invoke_model.return_value = {
                    'body': MagicMock(read=lambda: json.dumps({
                        'content': [{'text': 'Concurrent test summary'}]
                    }).encode())
                }
                
                def mock_client_factory(service_name, **kwargs):
                    if service_name == 's3':
                        return real_s3_client
                    elif service_name == 'stepfunctions':
                        return real_sf_client
                    elif service_name == 'secretsmanager':
                        return mock_secrets_client
                    elif service_name == 'bedrock-runtime':
                        return mock_bedrock_client
                    return MagicMock()
                
                mock_boto_client.side_effect = mock_client_factory
                
                try:
                    # Upload all emails concurrently
                    print(f"Uploading {len(test_emails)} emails concurrently to S3...")
                    
                    import concurrent.futures
                    
                    def upload_email(email_data, file_key):
                        self.s3_client.put_object(
                            Bucket=bucket_name,
                            Key=file_key,
                            Body=email_data['html'],
                            ContentType='text/html'
                        )
                        return file_key
                    
                    # Upload all files concurrently
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        upload_futures = [
                            executor.submit(upload_email, email, key)
                            for email, key in zip(test_emails, test_file_keys)
                        ]
                        
                        # Wait for all uploads to complete
                        uploaded_keys = [future.result() for future in concurrent.futures.as_completed(upload_futures)]
                    
                    print(f"Successfully uploaded {len(uploaded_keys)} files concurrently")
                    
                    # Wait for all workflows to process
                    time.sleep(10)
                    
                    # Verify multiple Step Function executions were triggered
                    state_machine_arn = self.stack_outputs.get('StateMachineArn')
                    if state_machine_arn:
                        executions = self.stepfunctions_client.list_executions(
                            stateMachineArn=state_machine_arn,
                            maxResults=20
                        )
                        
                        # Count recent executions (within last 60 seconds)
                        recent_executions = [
                            execution for execution in executions['executions']
                            if (time.time() - execution['startDate'].timestamp()) < 60
                        ]
                        
                        print(f"Found {len(recent_executions)} recent executions")
                        
                        # Should have at least as many executions as uploads
                        assert len(recent_executions) >= len(test_emails), f"Expected at least {len(test_emails)} executions, found {len(recent_executions)}"
                        
                        # Wait for all executions to complete
                        completed_executions = 0
                        max_wait_time = 120  # 2 minutes for concurrent processing
                        wait_interval = 5
                        waited_time = 0
                        
                        while waited_time < max_wait_time and completed_executions < len(recent_executions):
                            completed_executions = 0
                            
                            for execution in recent_executions:
                                execution_details = self.stepfunctions_client.describe_execution(
                                    executionArn=execution['executionArn']
                                )
                                
                                if execution_details['status'] in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                                    completed_executions += 1
                            
                            if completed_executions < len(recent_executions):
                                print(f"Waiting for executions to complete: {completed_executions}/{len(recent_executions)}")
                                time.sleep(wait_interval)
                                waited_time += wait_interval
                        
                        # Verify most executions succeeded
                        successful_executions = 0
                        for execution in recent_executions:
                            execution_details = self.stepfunctions_client.describe_execution(
                                executionArn=execution['executionArn']
                            )
                            
                            if execution_details['status'] == 'SUCCEEDED':
                                successful_executions += 1
                        
                        print(f"Successful executions: {successful_executions}/{len(recent_executions)}")
                        
                        # At least 80% should succeed (allowing for some concurrent processing issues)
                        success_rate = successful_executions / len(recent_executions)
                        assert success_rate >= 0.8, f"Success rate too low: {success_rate:.2%}"
                        
                        print("✅ Concurrent uploads test completed successfully!")
                    
                except Exception as e:
                    print(f"Concurrent uploads test failed: {e}")
                    raise
    
    def test_slack_message_formatting_validation(self):
        """Test that Slack messages are formatted correctly according to requirements"""
        # Skip if stack outputs not available
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Generate test email with specific article for format validation
        test_email = self.test_data.generate_medium_email_with_articles(1)
        
        # Create unique file key for this test
        test_file_key = f"test-emails/format-validation-test-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        # Track Slack messages for format validation
        slack_messages = []
        
        def capture_slack_post(*args, **kwargs):
            """Capture Slack POST requests for validation"""
            if 'json' in kwargs and 'summary' in kwargs['json']:
                slack_messages.append(kwargs['json']['summary'])
            
            # Return mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'ok': True}
            return mock_response
        
        # Mock external services
        with patch('requests.get') as mock_get, patch('requests.post', side_effect=capture_slack_post) as mock_post:
            mock_get.return_value.status_code = 200
            mock_get.return_value.text = self.test_data.generate_medium_article_html(
                "Format Validation Test Article", 
                "This is test content for validating the Slack message format according to requirements."
            )
            
            with patch('boto3.client') as mock_boto_client:
                real_s3_client = boto3.client('s3', region_name=self.region)
                real_sf_client = boto3.client('stepfunctions', region_name=self.region)
                
                mock_secrets_client = MagicMock()
                mock_secrets_client.get_secret_value.side_effect = [
                    {'SecretString': json.dumps({'cookies': 'test-cookies'})},
                    {'SecretString': json.dumps({'webhook_url': 'https://hooks.slack.com/test'})}
                ]
                
                mock_bedrock_client = MagicMock()
                mock_bedrock_client.invoke_model.return_value = {
                    'body': MagicMock(read=lambda: json.dumps({
                        'content': [{'text': 'This is a test summary for format validation.'}]
                    }).encode())
                }
                
                def mock_client_factory(service_name, **kwargs):
                    if service_name == 's3':
                        return real_s3_client
                    elif service_name == 'stepfunctions':
                        return real_sf_client
                    elif service_name == 'secretsmanager':
                        return mock_secrets_client
                    elif service_name == 'bedrock-runtime':
                        return mock_bedrock_client
                    return MagicMock()
                
                mock_boto_client.side_effect = mock_client_factory
                
                try:
                    # Upload test email
                    print(f"Uploading format validation test email to S3: s3://{bucket_name}/{test_file_key}")
                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=test_file_key,
                        Body=test_email['html'],
                        ContentType='text/html'
                    )
                    
                    # Wait for processing
                    time.sleep(8)
                    
                    # Verify Step Function execution completed
                    state_machine_arn = self.stack_outputs.get('StateMachineArn')
                    if state_machine_arn:
                        executions = self.stepfunctions_client.list_executions(
                            stateMachineArn=state_machine_arn,
                            maxResults=5
                        )
                        
                        recent_execution = None
                        for execution in executions['executions']:
                            if (time.time() - execution['startDate'].timestamp()) < 60:
                                recent_execution = execution
                                break
                        
                        if recent_execution:
                            # Wait for completion
                            execution_arn = recent_execution['executionArn']
                            max_wait_time = 45
                            wait_interval = 3
                            waited_time = 0
                            
                            while waited_time < max_wait_time:
                                execution_details = self.stepfunctions_client.describe_execution(
                                    executionArn=execution_arn
                                )
                                
                                if execution_details['status'] in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                                    break
                                
                                time.sleep(wait_interval)
                                waited_time += wait_interval
                            
                            # Verify Slack messages were captured and formatted correctly
                            assert len(slack_messages) > 0, "No Slack messages were captured"
                            
                            for message in slack_messages:
                                print(f"Validating Slack message format: {message}")
                                
                                # Verify required format: "📌 *{{title}}*\n\n📝 {{summary}}\n\n🔗 link：{{url}}"
                                assert '📌' in message, "Missing title emoji (📌)"
                                assert '📝' in message, "Missing summary emoji (📝)"
                                assert '🔗 link：' in message, "Missing link section (🔗 link：)"
                                
                                # Verify structure
                                lines = message.split('\n')
                                assert len(lines) >= 5, "Message should have at least 5 lines (title, empty, summary, empty, link)"
                                
                                # Verify title line starts with 📌 and has bold formatting
                                title_line = lines[0]
                                assert title_line.startswith('📌'), "Title line should start with 📌"
                                assert '*' in title_line, "Title should be bold (wrapped in *)"
                                
                                # Verify summary section starts with 📝
                                summary_line_found = False
                                for line in lines:
                                    if line.startswith('📝'):
                                        summary_line_found = True
                                        break
                                assert summary_line_found, "Summary line should start with 📝"
                                
                                # Verify link section
                                link_line_found = False
                                for line in lines:
                                    if line.startswith('🔗 link：'):
                                        link_line_found = True
                                        assert 'https://medium.com/' in line, "Link should contain Medium URL"
                                        break
                                assert link_line_found, "Link line should start with 🔗 link："
                                
                                print("✅ Slack message format validation passed")
                            
                            print("✅ All Slack message format validations completed successfully!")
                        
                except Exception as e:
                    print(f"Format validation test failed: {e}")
                    raise
    
    def test_article_processing_validation(self):
        """Test that all articles from email are processed and sent to Slack"""
        # Skip if stack outputs not available
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Generate test email with multiple articles for comprehensive validation
        num_articles = 3
        test_email = self.test_data.generate_medium_email_with_articles(num_articles)
        
        # Create unique file key for this test
        test_file_key = f"test-emails/article-validation-test-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        # Track processed articles and Slack messages
        processed_articles = []
        slack_messages = []
        
        def capture_article_fetch(*args, **kwargs):
            """Capture article fetch requests"""
            mock_response = MagicMock()
            mock_response.status_code = 200
            
            # Generate unique content for each article
            article_id = len(processed_articles) + 1
            article_title = f"Test Article {article_id}"
            article_content = f"This is comprehensive test content for article {article_id} that will be processed and summarized."
            
            mock_response.text = self.test_data.generate_medium_article_html(article_title, article_content)
            
            processed_articles.append({
                'title': article_title,
                'content': article_content,
                'url': args[0] if args else 'https://medium.com/test'
            })
            
            return mock_response
        
        def capture_slack_post(*args, **kwargs):
            """Capture Slack POST requests"""
            if 'json' in kwargs and 'summary' in kwargs['json']:
                slack_messages.append(kwargs['json']['summary'])
            
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {'ok': True}
            return mock_response
        
        # Mock external services
        with patch('requests.get', side_effect=capture_article_fetch) as mock_get, \
             patch('requests.post', side_effect=capture_slack_post) as mock_post:
            
            with patch('boto3.client') as mock_boto_client:
                real_s3_client = boto3.client('s3', region_name=self.region)
                real_sf_client = boto3.client('stepfunctions', region_name=self.region)
                
                mock_secrets_client = MagicMock()
                mock_secrets_client.get_secret_value.side_effect = [
                    {'SecretString': json.dumps({'cookies': 'test-cookies'})},
                    {'SecretString': json.dumps({'webhook_url': 'https://hooks.slack.com/test'})}
                ] * 10  # Multiple calls for multiple articles
                
                mock_bedrock_client = MagicMock()
                def mock_bedrock_invoke(*args, **kwargs):
                    # Generate unique summary for each article
                    summary_id = mock_bedrock_client.invoke_model.call_count + 1
                    return {
                        'body': MagicMock(read=lambda: json.dumps({
                            'content': [{'text': f'AI-generated summary for test article {summary_id}.'}]
                        }).encode())
                    }
                
                mock_bedrock_client.invoke_model.side_effect = mock_bedrock_invoke
                
                def mock_client_factory(service_name, **kwargs):
                    if service_name == 's3':
                        return real_s3_client
                    elif service_name == 'stepfunctions':
                        return real_sf_client
                    elif service_name == 'secretsmanager':
                        return mock_secrets_client
                    elif service_name == 'bedrock-runtime':
                        return mock_bedrock_client
                    return MagicMock()
                
                mock_boto_client.side_effect = mock_client_factory
                
                try:
                    # Upload test email
                    print(f"Uploading article validation test email with {num_articles} articles to S3: s3://{bucket_name}/{test_file_key}")
                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=test_file_key,
                        Body=test_email['html'],
                        ContentType='text/html'
                    )
                    
                    # Wait for processing
                    time.sleep(10)
                    
                    # Verify Step Function execution
                    state_machine_arn = self.stack_outputs.get('StateMachineArn')
                    if state_machine_arn:
                        executions = self.stepfunctions_client.list_executions(
                            stateMachineArn=state_machine_arn,
                            maxResults=5
                        )
                        
                        recent_execution = None
                        for execution in executions['executions']:
                            if (time.time() - execution['startDate'].timestamp()) < 60:
                                recent_execution = execution
                                break
                        
                        if recent_execution:
                            # Wait for completion
                            execution_arn = recent_execution['executionArn']
                            max_wait_time = 60
                            wait_interval = 3
                            waited_time = 0
                            
                            while waited_time < max_wait_time:
                                execution_details = self.stepfunctions_client.describe_execution(
                                    executionArn=execution_arn
                                )
                                
                                if execution_details['status'] in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                                    break
                                
                                time.sleep(wait_interval)
                                waited_time += wait_interval
                            
                            final_details = self.stepfunctions_client.describe_execution(
                                executionArn=execution_arn
                            )
                            
                            assert final_details['status'] == 'SUCCEEDED', f"Execution failed with status: {final_details['status']}"
                            
                            # Validate article processing
                            print(f"Processed articles: {len(processed_articles)}")
                            print(f"Slack messages sent: {len(slack_messages)}")
                            
                            # Verify all articles were fetched
                            assert len(processed_articles) == num_articles, f"Expected {num_articles} articles to be fetched, got {len(processed_articles)}"
                            
                            # Verify all articles were sent to Slack
                            assert len(slack_messages) == num_articles, f"Expected {num_articles} Slack messages, got {len(slack_messages)}"
                            
                            # Verify each Slack message corresponds to a processed article
                            for i, message in enumerate(slack_messages):
                                print(f"Validating Slack message {i+1}: {message[:100]}...")
                                
                                # Each message should contain the expected format and content
                                assert '📌' in message, f"Message {i+1} missing title emoji"
                                assert '📝' in message, f"Message {i+1} missing summary emoji"
                                assert '🔗 link：' in message, f"Message {i+1} missing link section"
                                assert 'medium.com' in message, f"Message {i+1} missing Medium URL"
                                
                                # Verify summary content is present
                                assert 'AI-generated summary' in message or 'summary' in message.lower(), f"Message {i+1} missing summary content"
                            
                            print("✅ All articles were successfully processed and sent to Slack!")
                            print(f"✅ Validated processing of {num_articles} articles with correct Slack formatting")
                        
                except Exception as e:
                    print(f"Article processing validation test failed: {e}")
                    raise

    @pytest.mark.skipif(True, reason="Performance test - run manually with --run-performance flag")
    def test_performance_with_large_email(self):
        """Test system performance with large email containing many articles"""
        # Skip if stack outputs not available
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Generate large email with many articles
        large_email = self.test_data.generate_performance_test_payload(10)
        
        # Create unique file key for this test
        test_file_key = f"test-emails/performance-test-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(test_file_key)
        
        start_time = time.time()
        
        try:
            # Upload large email
            print(f"Uploading large email with 10 articles to S3: s3://{bucket_name}/{test_file_key}")
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=test_file_key,
                Body=large_email['html'],
                ContentType='text/html'
            )
            
            # Wait for processing with extended timeout
            time.sleep(15)
            
            # Verify execution completed within reasonable time
            state_machine_arn = self.stack_outputs.get('StateMachineArn')
            if state_machine_arn:
                executions = self.stepfunctions_client.list_executions(
                    stateMachineArn=state_machine_arn,
                    maxResults=5
                )
                
                recent_execution = None
                for execution in executions['executions']:
                    if (time.time() - execution['startDate'].timestamp()) < 120:
                        recent_execution = execution
                        break
                
                if recent_execution:
                    # Wait for completion with extended timeout
                    execution_arn = recent_execution['executionArn']
                    max_wait_time = 300  # 5 minutes for large email
                    wait_interval = 10
                    waited_time = 0
                    
                    while waited_time < max_wait_time:
                        execution_details = self.stepfunctions_client.describe_execution(
                            executionArn=execution_arn
                        )
                        
                        if execution_details['status'] in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                            break
                        
                        time.sleep(wait_interval)
                        waited_time += wait_interval
                    
                    final_details = self.stepfunctions_client.describe_execution(
                        executionArn=execution_arn
                    )
                    
                    total_time = time.time() - start_time
                    print(f"Total processing time: {total_time:.2f} seconds")
                    
                    # Performance assertions
                    assert final_details['status'] == 'SUCCEEDED', "Large email processing should succeed"
                    assert total_time < 300, f"Processing took too long: {total_time:.2f} seconds"
                    
                    print("✅ Performance test completed successfully!")
            
        except Exception as e:
            print(f"Performance test failed: {e}")
            raise
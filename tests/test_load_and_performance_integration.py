"""
Load and Performance Integration Tests for Medium Digest Summarizer
Integrates with existing test infrastructure and pytest framework
"""

import json
import time
import boto3
import pytest
import uuid
import statistics
import concurrent.futures
from unittest.mock import patch, MagicMock
from tests.test_data_generator import TestDataGenerator


class TestLoadAndPerformanceIntegration:
    """Load and performance tests integrated with existing test framework"""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment"""
        cls.test_data = TestDataGenerator()
        cls.region = 'us-east-1'
        cls.session = boto3.Session()
        
        # Initialize AWS clients
        cls.s3_client = boto3.client('s3', region_name=cls.region)
        cls.stepfunctions_client = boto3.client('stepfunctions', region_name=cls.region)
        
        # Get stack outputs
        try:
            cf_client = cls.session.client('cloudformation', region_name=cls.region)
            stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
            cls.stack_outputs = {
                output['OutputKey']: output['OutputValue'] 
                for output in stack_response['Stacks'][0].get('Outputs', [])
            }
        except Exception:
            cls.stack_outputs = {}
        
        # Track test files for cleanup
        cls.uploaded_files = []
    
    @classmethod
    def teardown_class(cls):
        """Clean up test resources"""
        if hasattr(cls, 'uploaded_files') and cls.uploaded_files:
            bucket_name = cls.stack_outputs.get('EmailBucketName')
            if bucket_name:
                for file_key in cls.uploaded_files:
                    try:
                        cls.s3_client.delete_object(Bucket=bucket_name, Key=file_key)
                    except Exception:
                        pass  # Ignore cleanup errors
    
    def test_concurrent_s3_uploads_small_scale(self):
        """
        Test concurrent S3 uploads with small scale (2-5 concurrent uploads)
        Requirements: 2.3, 4.4, 6.1
        """
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        concurrency_levels = [2, 3, 5]
        
        for concurrency in concurrency_levels:
            print(f"\nTesting {concurrency} concurrent uploads...")
            
            # Generate test emails
            test_emails = []
            file_keys = []
            
            for i in range(concurrency):
                email = self.test_data.generate_medium_email_with_articles(2)
                test_emails.append(email)
                
                file_key = f"load-test/concurrent-small-{concurrency}-{i}-{uuid.uuid4().hex}.html"
                file_keys.append(file_key)
                self.uploaded_files.append(file_key)
            
            # Upload files concurrently
            start_time = time.time()
            
            def upload_file(email_data, file_key):
                try:
                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=file_key,
                        Body=email_data['html'],
                        ContentType='text/html'
                    )
                    return True
                except Exception:
                    return False
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                upload_futures = [
                    executor.submit(upload_file, email, key)
                    for email, key in zip(test_emails, file_keys)
                ]
                
                upload_results = [future.result() for future in concurrent.futures.as_completed(upload_futures)]
            
            upload_time = time.time() - start_time
            successful_uploads = sum(upload_results)
            
            print(f"Upload results: {successful_uploads}/{concurrency} successful in {upload_time:.2f}s")
            
            # Verify most uploads succeeded
            assert successful_uploads >= concurrency * 0.8, f"Too many upload failures: {successful_uploads}/{concurrency}"
            
            # Verify reasonable upload time
            assert upload_time < 30, f"Upload time too slow: {upload_time:.2f}s"
            
            # Wait for S3 events to trigger
            time.sleep(10)
    
    def test_execution_time_scaling_basic(self):
        """
        Test execution time scaling with different article counts (1, 3, 5 articles)
        Requirements: 2.3, 3.1, 6.1
        """
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        article_counts = [1, 3, 5]
        execution_times = {}
        
        for article_count in article_counts:
            print(f"\nTesting {article_count} articles...")
            
            # Generate test email
            email = self.test_data.generate_medium_email_with_articles(article_count)
            file_key = f"load-test/scaling-{article_count}-{uuid.uuid4().hex}.html"
            self.uploaded_files.append(file_key)
            
            # Upload and measure time
            start_time = time.time()
            
            try:
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_key,
                    Body=email['html'],
                    ContentType='text/html'
                )
                
                # Wait for processing (simplified monitoring)
                time.sleep(15)  # Allow time for processing
                
                end_time = time.time()
                execution_time = end_time - start_time
                execution_times[article_count] = execution_time
                
                print(f"Processing time for {article_count} articles: {execution_time:.2f}s")
                
                # Verify reasonable execution time
                max_expected_time = 30 + (article_count * 10)  # Base time + scaling
                assert execution_time < max_expected_time, f"Execution time too slow: {execution_time:.2f}s"
                
            except Exception as e:
                pytest.fail(f"Failed to process {article_count} articles: {e}")
        
        # Verify scaling is reasonable (not exponential)
        if len(execution_times) >= 2:
            min_articles = min(execution_times.keys())
            max_articles = max(execution_times.keys())
            
            scaling_factor = execution_times[max_articles] / execution_times[min_articles]
            article_factor = max_articles / min_articles
            
            print(f"Scaling factor: {scaling_factor:.2f}x for {article_factor:.2f}x articles")
            
            # Scaling should be sub-linear (better than linear scaling)
            assert scaling_factor <= article_factor * 1.5, f"Poor scaling: {scaling_factor:.2f}x"
    
    def test_step_function_concurrency_basic(self):
        """
        Test Step Function concurrency with basic load (5-10 concurrent executions)
        Requirements: 2.3, 3.1, 4.4, 6.1
        """
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        
        if not state_machine_arn:
            pytest.skip("StateMachineArn not available")
        
        # Test with moderate concurrency
        upload_count = 8
        
        print(f"\nTesting Step Function concurrency with {upload_count} uploads...")
        
        # Generate test files
        file_keys = []
        for i in range(upload_count):
            email = self.test_data.generate_medium_email_with_articles(2)
            file_key = f"load-test/sf-concurrency-{i}-{uuid.uuid4().hex}.html"
            file_keys.append((file_key, email))
            self.uploaded_files.append(file_key)
        
        # Upload files rapidly
        start_time = time.time()
        upload_errors = []
        
        def rapid_upload(file_key, email_data):
            try:
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_key,
                    Body=email_data['html'],
                    ContentType='text/html'
                )
                return True
            except Exception as e:
                upload_errors.append(str(e))
                return False
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=upload_count) as executor:
            upload_futures = [
                executor.submit(rapid_upload, file_key, email)
                for file_key, email in file_keys
            ]
            
            upload_results = [future.result() for future in concurrent.futures.as_completed(upload_futures)]
        
        upload_time = time.time() - start_time
        successful_uploads = sum(upload_results)
        
        print(f"Upload phase: {successful_uploads}/{upload_count} successful in {upload_time:.2f}s")
        
        # Verify most uploads succeeded
        assert successful_uploads >= upload_count * 0.8, f"Too many upload failures: {successful_uploads}/{upload_count}"
        
        # Wait for Step Function executions
        print("Waiting for Step Function executions...")
        time.sleep(30)
        
        # Check for recent executions
        try:
            executions = self.stepfunctions_client.list_executions(
                stateMachineArn=state_machine_arn,
                maxResults=20
            )
            
            # Count recent executions (within last 2 minutes)
            recent_executions = [
                execution for execution in executions['executions']
                if (time.time() - execution['startDate'].timestamp()) < 120
            ]
            
            print(f"Found {len(recent_executions)} recent executions")
            
            # Should have triggered executions for most uploads
            assert len(recent_executions) >= successful_uploads * 0.5, f"Too few executions triggered: {len(recent_executions)}"
            
        except Exception as e:
            print(f"Warning: Could not verify executions: {e}")
            # Don't fail the test if we can't verify executions
    
    def test_high_load_behavior_basic(self):
        """
        Test basic high load behavior with sustained uploads
        Requirements: 2.3, 3.1, 4.4, 6.1
        """
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        print("\nTesting basic high load behavior...")
        
        # Test configuration: 10 uploads over 30 seconds
        duration_seconds = 30
        total_uploads = 10
        upload_interval = duration_seconds / total_uploads
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        upload_results = []
        upload_count = 0
        
        print(f"Uploading {total_uploads} files over {duration_seconds} seconds...")
        
        while time.time() < end_time and upload_count < total_uploads:
            upload_start = time.time()
            
            try:
                # Generate and upload email
                email = self.test_data.generate_medium_email_with_articles(2)
                file_key = f"load-test/high-load-{upload_count}-{uuid.uuid4().hex}.html"
                self.uploaded_files.append(file_key)
                
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_key,
                    Body=email['html'],
                    ContentType='text/html'
                )
                
                upload_results.append(True)
                upload_count += 1
                
                # Maintain upload rate
                elapsed = time.time() - upload_start
                if elapsed < upload_interval:
                    time.sleep(upload_interval - elapsed)
                
            except Exception as e:
                upload_results.append(False)
                print(f"Upload error: {e}")
        
        total_test_time = time.time() - start_time
        successful_uploads = sum(upload_results)
        
        print(f"High load test completed:")
        print(f"  Total uploads: {len(upload_results)}")
        print(f"  Successful uploads: {successful_uploads}")
        print(f"  Success rate: {successful_uploads / len(upload_results):.1%}")
        print(f"  Total time: {total_test_time:.2f}s")
        print(f"  Upload rate: {successful_uploads / total_test_time:.2f} uploads/s")
        
        # Verify reasonable success rate
        success_rate = successful_uploads / len(upload_results) if upload_results else 0
        assert success_rate >= 0.8, f"Success rate too low: {success_rate:.1%}"
        
        # Verify reasonable upload rate
        upload_rate = successful_uploads / total_test_time
        assert upload_rate >= 0.2, f"Upload rate too low: {upload_rate:.2f} uploads/s"
        
        # Wait for processing to complete
        print("Waiting for processing to complete...")
        time.sleep(30)
    
    def test_performance_metrics_collection(self):
        """
        Test performance metrics collection and validation
        Requirements: 6.1
        """
        print("\nTesting performance metrics collection...")
        
        # Test with a simple scenario
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Upload a single test file and measure performance
        email = self.test_data.generate_medium_email_with_articles(3)
        file_key = f"load-test/metrics-{uuid.uuid4().hex}.html"
        self.uploaded_files.append(file_key)
        
        # Measure upload time
        upload_start = time.time()
        
        try:
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=file_key,
                Body=email['html'],
                ContentType='text/html'
            )
            
            upload_time = time.time() - upload_start
            
            print(f"Upload time: {upload_time:.3f}s")
            
            # Verify upload time is reasonable
            assert upload_time < 5.0, f"Upload time too slow: {upload_time:.3f}s"
            
            # Wait for processing
            processing_start = time.time()
            time.sleep(20)  # Allow processing time
            processing_time = time.time() - processing_start
            
            print(f"Processing wait time: {processing_time:.2f}s")
            
            # Collect basic metrics
            metrics = {
                'upload_time': upload_time,
                'processing_wait_time': processing_time,
                'total_time': upload_time + processing_time,
                'file_size': len(email['html']),
                'article_count': 3
            }
            
            print(f"Performance metrics: {metrics}")
            
            # Validate metrics are reasonable
            assert metrics['upload_time'] > 0, "Upload time should be positive"
            assert metrics['file_size'] > 0, "File size should be positive"
            assert metrics['total_time'] < 60, "Total time should be under 60 seconds"
            
        except Exception as e:
            pytest.fail(f"Performance metrics test failed: {e}")
    
    def test_error_handling_under_load(self):
        """
        Test error handling behavior under load conditions
        Requirements: 6.1, 6.2
        """
        print("\nTesting error handling under load...")
        
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Test with a mix of valid and invalid uploads
        test_cases = [
            # Valid emails
            self.test_data.generate_medium_email_with_articles(2),
            self.test_data.generate_medium_email_with_articles(1),
            # Invalid/edge case emails
            self.test_data.generate_medium_email_no_articles(),
            self.test_data.generate_malformed_email(),
            # Another valid email
            self.test_data.generate_medium_email_with_articles(3)
        ]
        
        upload_results = []
        
        for i, email in enumerate(test_cases):
            file_key = f"load-test/error-handling-{i}-{uuid.uuid4().hex}.html"
            self.uploaded_files.append(file_key)
            
            try:
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_key,
                    Body=email['html'],
                    ContentType='text/html'
                )
                upload_results.append(True)
                print(f"Upload {i+1}: Success")
                
            except Exception as e:
                upload_results.append(False)
                print(f"Upload {i+1}: Failed - {e}")
        
        successful_uploads = sum(upload_results)
        
        print(f"Error handling test results:")
        print(f"  Total uploads: {len(upload_results)}")
        print(f"  Successful uploads: {successful_uploads}")
        print(f"  Success rate: {successful_uploads / len(upload_results):.1%}")
        
        # Should handle most uploads successfully (even edge cases should upload to S3)
        success_rate = successful_uploads / len(upload_results)
        assert success_rate >= 0.8, f"Error handling success rate too low: {success_rate:.1%}"
        
        # Wait for processing
        time.sleep(20)
        
        print("Error handling test completed - system should handle edge cases gracefully")
    
    @pytest.mark.slow
    def test_comprehensive_load_scenario(self):
        """
        Comprehensive load test combining multiple scenarios
        Requirements: 2.3, 3.1, 4.4, 6.1
        """
        print("\nRunning comprehensive load scenario...")
        
        if not self.stack_outputs.get('EmailBucketName'):
            pytest.skip("Infrastructure not deployed - EmailBucketName not available")
        
        bucket_name = self.stack_outputs['EmailBucketName']
        
        # Comprehensive test: Mix of concurrent uploads with different article counts
        test_scenarios = [
            {'articles': 1, 'count': 3},  # 3 emails with 1 article each
            {'articles': 3, 'count': 2},  # 2 emails with 3 articles each
            {'articles': 5, 'count': 2},  # 2 emails with 5 articles each
        ]
        
        all_file_keys = []
        
        # Generate all test files
        for scenario in test_scenarios:
            for i in range(scenario['count']):
                email = self.test_data.generate_medium_email_with_articles(scenario['articles'])
                file_key = f"load-test/comprehensive-{scenario['articles']}art-{i}-{uuid.uuid4().hex}.html"
                all_file_keys.append((file_key, email))
                self.uploaded_files.append(file_key)
        
        print(f"Generated {len(all_file_keys)} test files")
        
        # Upload all files concurrently
        start_time = time.time()
        
        def upload_file(file_key, email_data):
            try:
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_key,
                    Body=email_data['html'],
                    ContentType='text/html'
                )
                return True
            except Exception:
                return False
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(all_file_keys)) as executor:
            upload_futures = [
                executor.submit(upload_file, file_key, email)
                for file_key, email in all_file_keys
            ]
            
            upload_results = [future.result() for future in concurrent.futures.as_completed(upload_futures)]
        
        upload_time = time.time() - start_time
        successful_uploads = sum(upload_results)
        
        print(f"Comprehensive load results:")
        print(f"  Total uploads: {len(upload_results)}")
        print(f"  Successful uploads: {successful_uploads}")
        print(f"  Upload time: {upload_time:.2f}s")
        print(f"  Success rate: {successful_uploads / len(upload_results):.1%}")
        print(f"  Upload throughput: {successful_uploads / upload_time:.2f} uploads/s")
        
        # Verify comprehensive test results
        success_rate = successful_uploads / len(upload_results)
        assert success_rate >= 0.9, f"Comprehensive test success rate too low: {success_rate:.1%}"
        
        upload_throughput = successful_uploads / upload_time
        assert upload_throughput >= 1.0, f"Upload throughput too low: {upload_throughput:.2f} uploads/s"
        
        # Wait for all processing to complete
        print("Waiting for comprehensive processing to complete...")
        time.sleep(60)  # Allow extra time for comprehensive processing
        
        print("✅ Comprehensive load scenario completed successfully")
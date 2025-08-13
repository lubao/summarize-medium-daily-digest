#!/usr/bin/env python3
"""
Load and Performance Testing for Medium Digest Summarizer
Tests concurrent S3 uploads, execution times, concurrency limits, and high load behavior
"""

import json
import time
import boto3
import uuid
import statistics
import concurrent.futures
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from tests.test_data_generator import TestDataGenerator


class LoadAndPerformanceTest:
    """Comprehensive load and performance testing suite"""
    
    def __init__(self):
        self.test_data = TestDataGenerator()
        self.region = 'us-east-1'
        self.session = boto3.Session()
        
        # Initialize AWS clients
        self.s3_client = boto3.client('s3', region_name=self.region)
        self.stepfunctions_client = boto3.client('stepfunctions', region_name=self.region)
        self.cloudwatch_client = boto3.client('cloudwatch', region_name=self.region)
        
        # Get stack outputs
        self.stack_outputs = self._get_stack_outputs()
        
        # Track uploaded files for cleanup
        self.uploaded_files = []
        self.test_executions = []
        
        # Performance metrics storage
        self.performance_metrics = {
            'concurrent_uploads': [],
            'execution_times': [],
            'article_scaling': {},
            'error_rates': {},
            'throughput_metrics': {}
        }
    
    def _get_stack_outputs(self) -> Dict[str, str]:
        """Get CloudFormation stack outputs"""
        try:
            cf_client = self.session.client('cloudformation', region_name=self.region)
            stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
            return {
                output['OutputKey']: output['OutputValue'] 
                for output in stack_response['Stacks'][0].get('Outputs', [])
            }
        except Exception as e:
            print(f"Warning: Could not get stack outputs: {e}")
            return {}
    
    def cleanup_test_resources(self):
        """Clean up test resources"""
        print("\n🧹 Cleaning up test resources...")
        
        # Clean up S3 files
        bucket_name = self.stack_outputs.get('EmailBucketName')
        if bucket_name and self.uploaded_files:
            for file_key in self.uploaded_files:
                try:
                    self.s3_client.delete_object(Bucket=bucket_name, Key=file_key)
                    print(f"  Deleted S3 object: {file_key}")
                except Exception as e:
                    print(f"  Failed to delete {file_key}: {e}")
        
        print(f"✅ Cleaned up {len(self.uploaded_files)} test files")
    
    def test_concurrent_s3_uploads(self, concurrency_levels: List[int] = [2, 5, 10, 15]) -> Dict[str, Any]:
        """
        Test multiple concurrent S3 uploads to validate parallel processing
        Requirements: 2.3, 4.4, 6.1
        """
        print("\n🚀 Testing concurrent S3 uploads...")
        
        if not self.stack_outputs.get('EmailBucketName'):
            print("❌ EmailBucketName not available - skipping concurrent upload test")
            return {'error': 'Infrastructure not available'}
        
        bucket_name = self.stack_outputs['EmailBucketName']
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        
        results = {}
        
        for concurrency in concurrency_levels:
            print(f"\n📊 Testing {concurrency} concurrent uploads...")
            
            # Generate test emails
            test_emails = []
            file_keys = []
            
            for i in range(concurrency):
                # Vary article count to test different payload sizes
                article_count = 2 + (i % 3)  # 2-4 articles per email
                email = self.test_data.generate_medium_email_with_articles(article_count)
                test_emails.append(email)
                
                file_key = f"load-test/concurrent-{concurrency}-{i}-{uuid.uuid4().hex}.html"
                file_keys.append(file_key)
                self.uploaded_files.append(file_key)
            
            # Upload files concurrently and measure performance
            start_time = time.time()
            upload_times = []
            upload_errors = []
            
            def upload_file(email_data: Dict, file_key: str) -> Tuple[str, float, bool]:
                """Upload single file and measure time"""
                upload_start = time.time()
                try:
                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=file_key,
                        Body=email_data['html'],
                        ContentType='text/html'
                    )
                    upload_time = time.time() - upload_start
                    return file_key, upload_time, True
                except Exception as e:
                    upload_time = time.time() - upload_start
                    upload_errors.append(str(e))
                    return file_key, upload_time, False
            
            # Execute concurrent uploads
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                upload_futures = [
                    executor.submit(upload_file, email, key)
                    for email, key in zip(test_emails, file_keys)
                ]
                
                upload_results = [future.result() for future in concurrent.futures.as_completed(upload_futures)]
            
            total_upload_time = time.time() - start_time
            
            # Analyze upload performance
            successful_uploads = sum(1 for _, _, success in upload_results if success)
            upload_times = [upload_time for _, upload_time, success in upload_results if success]
            
            if upload_times:
                avg_upload_time = statistics.mean(upload_times)
                max_upload_time = max(upload_times)
                upload_throughput = successful_uploads / total_upload_time
            else:
                avg_upload_time = max_upload_time = upload_throughput = 0
            
            print(f"  📤 Upload Results:")
            print(f"    Successful uploads: {successful_uploads}/{concurrency}")
            print(f"    Total upload time: {total_upload_time:.2f}s")
            print(f"    Average upload time: {avg_upload_time:.3f}s")
            print(f"    Max upload time: {max_upload_time:.3f}s")
            print(f"    Upload throughput: {upload_throughput:.2f} uploads/s")
            
            # Wait for Step Function executions to be triggered
            print("  ⏳ Waiting for Step Function executions...")
            time.sleep(10)  # Allow time for S3 events to trigger
            
            # Monitor Step Function executions
            execution_results = self._monitor_step_function_executions(
                state_machine_arn, 
                expected_count=successful_uploads,
                timeout_seconds=180  # 3 minutes for concurrent processing
            )
            
            # Calculate performance metrics
            results[concurrency] = {
                'upload_performance': {
                    'successful_uploads': successful_uploads,
                    'total_uploads': concurrency,
                    'success_rate': successful_uploads / concurrency,
                    'total_upload_time': total_upload_time,
                    'avg_upload_time': avg_upload_time,
                    'max_upload_time': max_upload_time,
                    'upload_throughput': upload_throughput,
                    'upload_errors': len(upload_errors)
                },
                'execution_performance': execution_results,
                'overall_performance': {
                    'end_to_end_time': execution_results.get('total_execution_time', 0),
                    'processing_throughput': execution_results.get('successful_executions', 0) / max(execution_results.get('total_execution_time', 1), 1)
                }
            }
            
            print(f"  ✅ Concurrency {concurrency} test completed")
            print(f"    End-to-end time: {execution_results.get('total_execution_time', 0):.2f}s")
            print(f"    Processing throughput: {results[concurrency]['overall_performance']['processing_throughput']:.2f} workflows/s")
        
        # Analyze scaling behavior
        self._analyze_concurrency_scaling(results)
        
        return results
    
    def test_execution_time_scaling(self, article_counts: List[int] = [1, 3, 5, 10, 15, 20]) -> Dict[str, Any]:
        """
        Measure execution times for different email sizes and article counts
        Requirements: 2.3, 3.1, 6.1
        """
        print("\n📈 Testing execution time scaling with article count...")
        
        if not self.stack_outputs.get('EmailBucketName'):
            print("❌ EmailBucketName not available - skipping scaling test")
            return {'error': 'Infrastructure not available'}
        
        bucket_name = self.stack_outputs['EmailBucketName']
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        
        results = {}
        
        for article_count in article_counts:
            print(f"\n📊 Testing {article_count} articles...")
            
            # Run multiple iterations for statistical significance
            execution_times = []
            processing_results = []
            
            for iteration in range(3):  # 3 iterations per article count
                print(f"  Iteration {iteration + 1}/3...")
                
                # Generate test email
                email = self.test_data.generate_medium_email_with_articles(article_count)
                file_key = f"load-test/scaling-{article_count}-{iteration}-{uuid.uuid4().hex}.html"
                self.uploaded_files.append(file_key)
                
                # Upload and measure end-to-end time
                start_time = time.time()
                
                try:
                    self.s3_client.put_object(
                        Bucket=bucket_name,
                        Key=file_key,
                        Body=email['html'],
                        ContentType='text/html'
                    )
                    
                    # Wait for execution to complete
                    time.sleep(5)  # Allow S3 event processing
                    
                    execution_result = self._monitor_step_function_executions(
                        state_machine_arn,
                        expected_count=1,
                        timeout_seconds=120,
                        start_time=start_time
                    )
                    
                    end_to_end_time = time.time() - start_time
                    execution_times.append(end_to_end_time)
                    processing_results.append(execution_result)
                    
                    print(f"    End-to-end time: {end_to_end_time:.2f}s")
                    
                except Exception as e:
                    print(f"    ❌ Iteration failed: {e}")
                    continue
            
            # Calculate statistics
            if execution_times:
                results[article_count] = {
                    'execution_times': execution_times,
                    'avg_execution_time': statistics.mean(execution_times),
                    'median_execution_time': statistics.median(execution_times),
                    'min_execution_time': min(execution_times),
                    'max_execution_time': max(execution_times),
                    'std_deviation': statistics.stdev(execution_times) if len(execution_times) > 1 else 0,
                    'processing_results': processing_results,
                    'success_rate': sum(1 for r in processing_results if r.get('successful_executions', 0) > 0) / len(processing_results)
                }
                
                print(f"  📊 Results for {article_count} articles:")
                print(f"    Average time: {results[article_count]['avg_execution_time']:.2f}s")
                print(f"    Min/Max time: {results[article_count]['min_execution_time']:.2f}s / {results[article_count]['max_execution_time']:.2f}s")
                print(f"    Success rate: {results[article_count]['success_rate']:.1%}")
        
        # Analyze scaling patterns
        self._analyze_execution_time_scaling(results)
        
        return results
    
    def test_step_function_concurrency_limits(self) -> Dict[str, Any]:
        """
        Validate Step Function concurrency limits and error handling
        Requirements: 2.3, 3.1, 4.4, 6.1
        """
        print("\n🔄 Testing Step Function concurrency limits...")
        
        if not self.stack_outputs.get('StateMachineArn'):
            print("❌ StateMachineArn not available - skipping concurrency limits test")
            return {'error': 'Infrastructure not available'}
        
        state_machine_arn = self.stack_outputs['StateMachineArn']
        bucket_name = self.stack_outputs.get('EmailBucketName')
        
        # Test different concurrency scenarios
        concurrency_tests = [
            {'name': 'Low Concurrency', 'uploads': 5, 'articles_per_email': 3},
            {'name': 'Medium Concurrency', 'uploads': 10, 'articles_per_email': 5},
            {'name': 'High Concurrency', 'uploads': 20, 'articles_per_email': 2},
            {'name': 'Burst Load', 'uploads': 30, 'articles_per_email': 1}
        ]
        
        results = {}
        
        for test_config in concurrency_tests:
            test_name = test_config['name']
            upload_count = test_config['uploads']
            articles_per_email = test_config['articles_per_email']
            
            print(f"\n🧪 Running {test_name} test ({upload_count} uploads, {articles_per_email} articles each)...")
            
            # Generate test files
            file_keys = []
            for i in range(upload_count):
                email = self.test_data.generate_medium_email_with_articles(articles_per_email)
                file_key = f"load-test/concurrency-{test_name.lower().replace(' ', '-')}-{i}-{uuid.uuid4().hex}.html"
                file_keys.append((file_key, email))
                self.uploaded_files.append(file_key)
            
            # Upload all files rapidly to test concurrency limits
            start_time = time.time()
            upload_errors = []
            
            def rapid_upload(file_key: str, email_data: Dict) -> bool:
                """Upload file as quickly as possible"""
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
            
            # Execute rapid uploads
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(upload_count, 20)) as executor:
                upload_futures = [
                    executor.submit(rapid_upload, file_key, email)
                    for file_key, email in file_keys
                ]
                
                upload_results = [future.result() for future in concurrent.futures.as_completed(upload_futures)]
            
            upload_time = time.time() - start_time
            successful_uploads = sum(upload_results)
            
            print(f"  📤 Upload phase completed in {upload_time:.2f}s")
            print(f"    Successful uploads: {successful_uploads}/{upload_count}")
            print(f"    Upload errors: {len(upload_errors)}")
            
            # Monitor Step Function behavior under load
            print("  ⏳ Monitoring Step Function executions...")
            time.sleep(15)  # Allow time for all S3 events to trigger
            
            execution_monitoring = self._monitor_step_function_executions(
                state_machine_arn,
                expected_count=successful_uploads,
                timeout_seconds=300,  # 5 minutes for high concurrency
                detailed_monitoring=True
            )
            
            # Analyze concurrency behavior
            results[test_name] = {
                'test_config': test_config,
                'upload_performance': {
                    'total_uploads': upload_count,
                    'successful_uploads': successful_uploads,
                    'upload_time': upload_time,
                    'upload_rate': successful_uploads / upload_time,
                    'upload_errors': len(upload_errors)
                },
                'execution_monitoring': execution_monitoring,
                'concurrency_analysis': self._analyze_concurrency_behavior(execution_monitoring)
            }
            
            print(f"  ✅ {test_name} completed:")
            print(f"    Execution success rate: {execution_monitoring.get('success_rate', 0):.1%}")
            print(f"    Average execution time: {execution_monitoring.get('avg_execution_time', 0):.2f}s")
            print(f"    Concurrent executions detected: {execution_monitoring.get('max_concurrent_executions', 0)}")
        
        return results
    
    def test_high_load_behavior(self) -> Dict[str, Any]:
        """
        Test system behavior under high load conditions
        Requirements: 2.3, 3.1, 4.4, 6.1
        """
        print("\n🔥 Testing high load behavior...")
        
        if not self.stack_outputs.get('EmailBucketName'):
            print("❌ EmailBucketName not available - skipping high load test")
            return {'error': 'Infrastructure not available'}
        
        bucket_name = self.stack_outputs['EmailBucketName']
        state_machine_arn = self.stack_outputs.get('StateMachineArn')
        
        # High load test configuration
        load_tests = [
            {
                'name': 'Sustained Load',
                'duration_seconds': 60,
                'uploads_per_second': 2,
                'articles_per_email': 3
            },
            {
                'name': 'Burst Load',
                'duration_seconds': 30,
                'uploads_per_second': 5,
                'articles_per_email': 2
            },
            {
                'name': 'Stress Test',
                'duration_seconds': 45,
                'uploads_per_second': 3,
                'articles_per_email': 5
            }
        ]
        
        results = {}
        
        for load_test in load_tests:
            test_name = load_test['name']
            duration = load_test['duration_seconds']
            rate = load_test['uploads_per_second']
            articles = load_test['articles_per_email']
            
            print(f"\n🧪 Running {test_name}...")
            print(f"  Duration: {duration}s, Rate: {rate} uploads/s, Articles: {articles}")
            
            # Execute sustained load test
            load_results = self._execute_sustained_load_test(
                bucket_name=bucket_name,
                state_machine_arn=state_machine_arn,
                duration_seconds=duration,
                uploads_per_second=rate,
                articles_per_email=articles,
                test_name=test_name
            )
            
            results[test_name] = load_results
            
            print(f"  ✅ {test_name} completed:")
            print(f"    Total uploads: {load_results.get('total_uploads', 0)}")
            print(f"    Success rate: {load_results.get('success_rate', 0):.1%}")
            print(f"    Average response time: {load_results.get('avg_response_time', 0):.2f}s")
            print(f"    Error rate: {load_results.get('error_rate', 0):.1%}")
            
            # Cool down between tests
            if test_name != load_tests[-1]['name']:
                print("  ⏸️  Cooling down for 30 seconds...")
                time.sleep(30)
        
        # Analyze overall high load behavior
        self._analyze_high_load_behavior(results)
        
        return results
    
    def _execute_sustained_load_test(self, bucket_name: str, state_machine_arn: str, 
                                   duration_seconds: int, uploads_per_second: float,
                                   articles_per_email: int, test_name: str) -> Dict[str, Any]:
        """Execute a sustained load test with specified parameters"""
        
        start_time = time.time()
        end_time = start_time + duration_seconds
        
        upload_interval = 1.0 / uploads_per_second
        
        upload_results = []
        upload_times = []
        upload_errors = []
        
        upload_count = 0
        
        print(f"    Starting sustained load test for {duration_seconds}s...")
        
        while time.time() < end_time:
            upload_start = time.time()
            
            # Generate and upload email
            try:
                email = self.test_data.generate_medium_email_with_articles(articles_per_email)
                file_key = f"load-test/sustained-{test_name.lower().replace(' ', '-')}-{upload_count}-{uuid.uuid4().hex}.html"
                self.uploaded_files.append(file_key)
                
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=file_key,
                    Body=email['html'],
                    ContentType='text/html'
                )
                
                upload_time = time.time() - upload_start
                upload_times.append(upload_time)
                upload_results.append(True)
                upload_count += 1
                
                # Maintain upload rate
                elapsed = time.time() - upload_start
                if elapsed < upload_interval:
                    time.sleep(upload_interval - elapsed)
                
            except Exception as e:
                upload_time = time.time() - upload_start
                upload_errors.append(str(e))
                upload_results.append(False)
                print(f"    Upload error: {e}")
        
        total_test_time = time.time() - start_time
        successful_uploads = sum(upload_results)
        
        print(f"    Upload phase completed: {successful_uploads}/{len(upload_results)} successful")
        
        # Monitor executions during and after the load test
        print("    Monitoring Step Function executions...")
        time.sleep(30)  # Allow processing to catch up
        
        execution_monitoring = self._monitor_step_function_executions(
            state_machine_arn,
            expected_count=successful_uploads,
            timeout_seconds=180,
            start_time=start_time
        )
        
        return {
            'test_config': {
                'duration_seconds': duration_seconds,
                'uploads_per_second': uploads_per_second,
                'articles_per_email': articles_per_email
            },
            'upload_performance': {
                'total_uploads': len(upload_results),
                'successful_uploads': successful_uploads,
                'upload_errors': len(upload_errors),
                'success_rate': successful_uploads / len(upload_results) if upload_results else 0,
                'actual_upload_rate': successful_uploads / total_test_time,
                'avg_upload_time': statistics.mean(upload_times) if upload_times else 0,
                'max_upload_time': max(upload_times) if upload_times else 0
            },
            'execution_performance': execution_monitoring,
            'overall_metrics': {
                'total_test_time': total_test_time,
                'end_to_end_success_rate': execution_monitoring.get('success_rate', 0),
                'avg_response_time': execution_monitoring.get('avg_execution_time', 0),
                'error_rate': 1 - execution_monitoring.get('success_rate', 0)
            }
        }
    
    def _monitor_step_function_executions(self, state_machine_arn: str, expected_count: int,
                                        timeout_seconds: int, start_time: float = None,
                                        detailed_monitoring: bool = False) -> Dict[str, Any]:
        """Monitor Step Function executions and collect performance metrics"""
        
        if not state_machine_arn:
            return {'error': 'StateMachineArn not available'}
        
        monitor_start = start_time or time.time()
        monitor_end = monitor_start + timeout_seconds
        
        executions_found = []
        execution_details = []
        
        print(f"    Monitoring executions for up to {timeout_seconds}s...")
        
        # Monitor executions
        while time.time() < monitor_end:
            try:
                # Get recent executions
                response = self.stepfunctions_client.list_executions(
                    stateMachineArn=state_machine_arn,
                    maxResults=50
                )
                
                # Filter executions that started after our test began
                recent_executions = [
                    execution for execution in response['executions']
                    if execution['startDate'].timestamp() >= monitor_start - 10  # 10s buffer
                ]
                
                # Track new executions
                for execution in recent_executions:
                    if execution['executionArn'] not in [e['executionArn'] for e in executions_found]:
                        executions_found.append(execution)
                
                # Check if we have enough executions
                if len(executions_found) >= expected_count:
                    print(f"    Found {len(executions_found)} executions (expected {expected_count})")
                    break
                
                time.sleep(2)  # Check every 2 seconds
                
            except Exception as e:
                print(f"    Error monitoring executions: {e}")
                break
        
        # Wait for executions to complete
        print(f"    Waiting for {len(executions_found)} executions to complete...")
        
        completed_executions = 0
        max_concurrent = 0
        
        while time.time() < monitor_end and completed_executions < len(executions_found):
            running_count = 0
            completed_count = 0
            
            for execution in executions_found:
                try:
                    details = self.stepfunctions_client.describe_execution(
                        executionArn=execution['executionArn']
                    )
                    
                    status = details['status']
                    if status == 'RUNNING':
                        running_count += 1
                    elif status in ['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED']:
                        completed_count += 1
                        
                        # Store detailed execution info
                        if detailed_monitoring and details not in execution_details:
                            execution_details.append(details)
                
                except Exception as e:
                    print(f"    Error getting execution details: {e}")
            
            max_concurrent = max(max_concurrent, running_count)
            completed_executions = completed_count
            
            if completed_executions < len(executions_found):
                print(f"    Progress: {completed_executions}/{len(executions_found)} completed, {running_count} running")
                time.sleep(5)
        
        # Collect final execution results
        successful_executions = 0
        failed_executions = 0
        execution_times = []
        
        for execution in executions_found:
            try:
                details = self.stepfunctions_client.describe_execution(
                    executionArn=execution['executionArn']
                )
                
                status = details['status']
                if status == 'SUCCEEDED':
                    successful_executions += 1
                elif status in ['FAILED', 'TIMED_OUT', 'ABORTED']:
                    failed_executions += 1
                
                # Calculate execution time
                if 'stopDate' in details:
                    execution_time = (details['stopDate'] - details['startDate']).total_seconds()
                    execution_times.append(execution_time)
                
            except Exception as e:
                print(f"    Error getting final execution details: {e}")
                failed_executions += 1
        
        total_executions = len(executions_found)
        success_rate = successful_executions / total_executions if total_executions > 0 else 0
        
        monitoring_results = {
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'failed_executions': failed_executions,
            'success_rate': success_rate,
            'max_concurrent_executions': max_concurrent,
            'total_execution_time': time.time() - monitor_start,
            'execution_times': execution_times,
            'avg_execution_time': statistics.mean(execution_times) if execution_times else 0,
            'median_execution_time': statistics.median(execution_times) if execution_times else 0,
            'min_execution_time': min(execution_times) if execution_times else 0,
            'max_execution_time': max(execution_times) if execution_times else 0
        }
        
        if detailed_monitoring:
            monitoring_results['execution_details'] = execution_details
        
        return monitoring_results
    
    def _analyze_concurrency_scaling(self, results: Dict[str, Any]):
        """Analyze concurrency scaling behavior"""
        print("\n📊 Concurrency Scaling Analysis:")
        
        concurrency_levels = sorted(results.keys())
        throughputs = []
        success_rates = []
        
        for level in concurrency_levels:
            if isinstance(level, int) and 'overall_performance' in results[level]:
                throughput = results[level]['overall_performance']['processing_throughput']
                success_rate = results[level]['upload_performance']['success_rate']
                
                throughputs.append(throughput)
                success_rates.append(success_rate)
                
                print(f"  Concurrency {level}: {throughput:.2f} workflows/s, {success_rate:.1%} success")
        
        # Identify optimal concurrency level
        if throughputs:
            max_throughput_idx = throughputs.index(max(throughputs))
            optimal_concurrency = concurrency_levels[max_throughput_idx]
            print(f"  🎯 Optimal concurrency level: {optimal_concurrency} ({max(throughputs):.2f} workflows/s)")
        
        # Check for performance degradation
        if len(throughputs) >= 2:
            throughput_trend = throughputs[-1] / throughputs[0] if throughputs[0] > 0 else 0
            if throughput_trend < 0.8:
                print(f"  ⚠️  Performance degradation detected: {throughput_trend:.2f}x scaling")
            else:
                print(f"  ✅ Good scaling performance: {throughput_trend:.2f}x scaling")
    
    def _analyze_execution_time_scaling(self, results: Dict[str, Any]):
        """Analyze execution time scaling with article count"""
        print("\n📈 Execution Time Scaling Analysis:")
        
        article_counts = sorted(results.keys())
        
        for count in article_counts:
            if count in results:
                avg_time = results[count]['avg_execution_time']
                success_rate = results[count]['success_rate']
                print(f"  {count} articles: {avg_time:.2f}s avg, {success_rate:.1%} success")
        
        # Calculate scaling efficiency
        if len(article_counts) >= 2:
            base_count = article_counts[0]
            base_time = results[base_count]['avg_execution_time']
            
            for count in article_counts[1:]:
                if count in results:
                    current_time = results[count]['avg_execution_time']
                    scaling_factor = current_time / base_time if base_time > 0 else 0
                    efficiency = (count / base_count) / scaling_factor if scaling_factor > 0 else 0
                    
                    print(f"  Scaling {base_count}→{count} articles: {scaling_factor:.2f}x time, {efficiency:.2f} efficiency")
    
    def _analyze_concurrency_behavior(self, execution_monitoring: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze Step Function concurrency behavior"""
        return {
            'max_concurrent_executions': execution_monitoring.get('max_concurrent_executions', 0),
            'concurrency_efficiency': execution_monitoring.get('success_rate', 0),
            'avg_execution_time_under_load': execution_monitoring.get('avg_execution_time', 0),
            'execution_time_variance': statistics.stdev(execution_monitoring.get('execution_times', [0])) if len(execution_monitoring.get('execution_times', [])) > 1 else 0
        }
    
    def _analyze_high_load_behavior(self, results: Dict[str, Any]):
        """Analyze high load test results"""
        print("\n🔥 High Load Behavior Analysis:")
        
        for test_name, result in results.items():
            if 'overall_metrics' in result:
                metrics = result['overall_metrics']
                print(f"  {test_name}:")
                print(f"    Success rate: {metrics.get('end_to_end_success_rate', 0):.1%}")
                print(f"    Average response time: {metrics.get('avg_response_time', 0):.2f}s")
                print(f"    Error rate: {metrics.get('error_rate', 0):.1%}")
        
        # Overall system stability assessment
        overall_success_rates = [
            result['overall_metrics']['end_to_end_success_rate']
            for result in results.values()
            if 'overall_metrics' in result
        ]
        
        if overall_success_rates:
            avg_success_rate = statistics.mean(overall_success_rates)
            min_success_rate = min(overall_success_rates)
            
            print(f"\n  📊 Overall System Stability:")
            print(f"    Average success rate: {avg_success_rate:.1%}")
            print(f"    Minimum success rate: {min_success_rate:.1%}")
            
            if min_success_rate >= 0.95:
                print("    ✅ Excellent stability under high load")
            elif min_success_rate >= 0.90:
                print("    ✅ Good stability under high load")
            elif min_success_rate >= 0.80:
                print("    ⚠️  Acceptable stability, some degradation under high load")
            else:
                print("    ❌ Poor stability under high load - needs optimization")
    
    def generate_performance_report(self, test_results: Dict[str, Any]) -> str:
        """Generate comprehensive performance report"""
        report = []
        report.append("# Medium Digest Summarizer - Load and Performance Test Report")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Executive Summary
        report.append("## Executive Summary")
        report.append("")
        
        # Test Results Summary
        for test_name, results in test_results.items():
            if isinstance(results, dict) and 'error' not in results:
                report.append(f"### {test_name}")
                
                if 'concurrent_uploads' in test_name.lower():
                    # Concurrent uploads summary
                    max_concurrency = max(results.keys()) if results else 0
                    report.append(f"- Maximum tested concurrency: {max_concurrency}")
                    
                    if max_concurrency in results:
                        best_result = results[max_concurrency]
                        success_rate = best_result.get('upload_performance', {}).get('success_rate', 0)
                        throughput = best_result.get('overall_performance', {}).get('processing_throughput', 0)
                        report.append(f"- Success rate at max concurrency: {success_rate:.1%}")
                        report.append(f"- Processing throughput: {throughput:.2f} workflows/s")
                
                elif 'execution_time' in test_name.lower():
                    # Execution time scaling summary
                    max_articles = max(results.keys()) if results else 0
                    report.append(f"- Maximum tested article count: {max_articles}")
                    
                    if max_articles in results:
                        max_result = results[max_articles]
                        avg_time = max_result.get('avg_execution_time', 0)
                        success_rate = max_result.get('success_rate', 0)
                        report.append(f"- Average execution time for {max_articles} articles: {avg_time:.2f}s")
                        report.append(f"- Success rate: {success_rate:.1%}")
                
                report.append("")
        
        # Detailed Results
        report.append("## Detailed Test Results")
        report.append("")
        
        for test_name, results in test_results.items():
            if isinstance(results, dict) and 'error' not in results:
                report.append(f"### {test_name}")
                report.append("```json")
                report.append(json.dumps(results, indent=2, default=str))
                report.append("```")
                report.append("")
        
        # Performance Recommendations
        report.append("## Performance Recommendations")
        report.append("")
        report.append("Based on the load and performance testing results:")
        report.append("")
        report.append("1. **Concurrency Optimization**: Monitor Step Function concurrency limits")
        report.append("2. **Scaling Efficiency**: Consider optimizing for larger article counts")
        report.append("3. **Error Handling**: Ensure robust error handling under high load")
        report.append("4. **Resource Allocation**: Review Lambda memory and timeout settings")
        report.append("5. **Monitoring**: Implement comprehensive performance monitoring")
        report.append("")
        
        return "\n".join(report)
    
    def run_all_load_tests(self) -> Dict[str, Any]:
        """Run all load and performance tests"""
        print("🚀 Starting comprehensive load and performance testing...")
        print("=" * 80)
        
        all_results = {}
        
        try:
            # Test 1: Concurrent S3 uploads
            print("\n1️⃣ Testing concurrent S3 uploads...")
            concurrent_results = self.test_concurrent_s3_uploads()
            all_results['concurrent_s3_uploads'] = concurrent_results
            
            # Test 2: Execution time scaling
            print("\n2️⃣ Testing execution time scaling...")
            scaling_results = self.test_execution_time_scaling()
            all_results['execution_time_scaling'] = scaling_results
            
            # Test 3: Step Function concurrency limits
            print("\n3️⃣ Testing Step Function concurrency limits...")
            concurrency_results = self.test_step_function_concurrency_limits()
            all_results['step_function_concurrency'] = concurrency_results
            
            # Test 4: High load behavior
            print("\n4️⃣ Testing high load behavior...")
            high_load_results = self.test_high_load_behavior()
            all_results['high_load_behavior'] = high_load_results
            
            # Generate performance report
            print("\n📊 Generating performance report...")
            performance_report = self.generate_performance_report(all_results)
            
            # Save report to file
            with open('load_performance_test_report.md', 'w') as f:
                f.write(performance_report)
            
            print("✅ Performance report saved to: load_performance_test_report.md")
            
        except Exception as e:
            print(f"❌ Load testing failed: {e}")
            all_results['error'] = str(e)
        
        finally:
            # Cleanup test resources
            self.cleanup_test_resources()
        
        print("\n" + "=" * 80)
        print("🏁 Load and performance testing completed!")
        
        return all_results


def main():
    """Main function to run load and performance tests"""
    load_tester = LoadAndPerformanceTest()
    
    try:
        results = load_tester.run_all_load_tests()
        
        # Print summary
        print("\n📋 Test Summary:")
        for test_name, result in results.items():
            if isinstance(result, dict) and 'error' not in result:
                print(f"✅ {test_name}: Completed")
            else:
                print(f"❌ {test_name}: Failed")
        
        return results
        
    except KeyboardInterrupt:
        print("\n⏹️  Testing interrupted by user")
        load_tester.cleanup_test_resources()
        return {'error': 'Interrupted by user'}
    
    except Exception as e:
        print(f"\n❌ Testing failed with error: {e}")
        load_tester.cleanup_test_resources()
        return {'error': str(e)}


if __name__ == "__main__":
    main()
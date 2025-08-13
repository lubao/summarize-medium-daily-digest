"""
Performance testing for Medium Digest Summarizer
Tests concurrent article processing and system scalability
"""

import json
import time
import statistics
import concurrent.futures
from unittest.mock import patch, MagicMock
from tests.test_data_generator import TestDataGenerator


class TestPerformance:
    """Performance testing suite"""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment"""
        cls.test_data = TestDataGenerator()
    
    def test_single_article_processing_time(self):
        """Measure processing time for single article"""
        test_email = self.test_data.generate_medium_email_with_articles(1)
        payload = {"payload": json.dumps(test_email)}
        
        execution_times = []
        
        for _ in range(10):  # Run 10 iterations
            start_time = time.time()
            
            with patch('boto3.client') as mock_boto_client:
                self._setup_performance_mocks(mock_boto_client, 1)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                execution_time = time.time() - start_time
                execution_times.append(execution_time)
                
                assert response['statusCode'] == 200
        
        # Calculate performance metrics
        avg_time = statistics.mean(execution_times)
        median_time = statistics.median(execution_times)
        max_time = max(execution_times)
        min_time = min(execution_times)
        
        print(f"\nSingle Article Performance Metrics:")
        print(f"Average: {avg_time:.3f}s")
        print(f"Median: {median_time:.3f}s")
        print(f"Min: {min_time:.3f}s")
        print(f"Max: {max_time:.3f}s")
        
        # Performance assertions
        assert avg_time < 1.0, f"Average processing time too high: {avg_time:.3f}s"
        assert max_time < 2.0, f"Maximum processing time too high: {max_time:.3f}s"
    
    def test_multiple_articles_processing_time(self):
        """Measure processing time scaling with number of articles"""
        article_counts = [1, 3, 5, 10]
        results = {}
        
        for count in article_counts:
            test_email = self.test_data.generate_performance_test_payload(count)
            payload = {"payload": json.dumps(test_email)}
            
            execution_times = []
            
            for _ in range(5):  # Run 5 iterations per count
                start_time = time.time()
                
                with patch('boto3.client') as mock_boto_client:
                    self._setup_performance_mocks(mock_boto_client, count)
                    
                    from lambdas.trigger import lambda_handler as trigger_handler
                    
                    event = {
                        'body': json.dumps(payload),
                        'headers': {'Content-Type': 'application/json'}
                    }
                    
                    response = trigger_handler(event, {})
                    execution_time = time.time() - start_time
                    execution_times.append(execution_time)
                    
                    assert response['statusCode'] == 200
            
            avg_time = statistics.mean(execution_times)
            results[count] = avg_time
            
            print(f"\n{count} Articles - Average: {avg_time:.3f}s")
        
        # Verify scaling is reasonable (not exponential)
        # Processing 10 articles shouldn't take more than 5x single article time
        single_article_time = results[1]
        ten_article_time = results[10]
        scaling_factor = ten_article_time / single_article_time
        
        print(f"\nScaling factor (10 articles vs 1): {scaling_factor:.2f}x")
        assert scaling_factor < 5.0, f"Poor scaling: {scaling_factor:.2f}x"
    
    def test_concurrent_processing_performance(self):
        """Test performance under concurrent load"""
        concurrent_levels = [1, 2, 5, 10]
        results = {}
        
        for concurrency in concurrent_levels:
            payloads = self.test_data.generate_concurrent_test_payloads(concurrency)
            
            def make_request(payload):
                start_time = time.time()
                
                with patch('boto3.client') as mock_boto_client:
                    self._setup_performance_mocks(mock_boto_client, 2)
                    
                    from lambdas.trigger import lambda_handler as trigger_handler
                    
                    event = {
                        'body': json.dumps(payload),
                        'headers': {'Content-Type': 'application/json'}
                    }
                    
                    response = trigger_handler(event, {})
                    execution_time = time.time() - start_time
                    
                    return response, execution_time
            
            start_time = time.time()
            
            # Execute concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = [executor.submit(make_request, payload) for payload in payloads]
                request_results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            total_time = time.time() - start_time
            
            # Verify all requests succeeded
            individual_times = []
            for response, execution_time in request_results:
                assert response['statusCode'] == 200
                individual_times.append(execution_time)
            
            avg_individual_time = statistics.mean(individual_times)
            results[concurrency] = {
                'total_time': total_time,
                'avg_individual_time': avg_individual_time,
                'throughput': concurrency / total_time
            }
            
            print(f"\nConcurrency {concurrency}:")
            print(f"  Total time: {total_time:.3f}s")
            print(f"  Avg individual: {avg_individual_time:.3f}s")
            print(f"  Throughput: {results[concurrency]['throughput']:.2f} req/s")
        
        # Verify throughput improves with concurrency (up to a point)
        single_throughput = results[1]['throughput']
        concurrent_throughput = results[5]['throughput']
        
        print(f"\nThroughput improvement (5 concurrent vs 1): {concurrent_throughput / single_throughput:.2f}x")
        assert concurrent_throughput > single_throughput, "Concurrency should improve throughput"
    
    def test_memory_usage_scaling(self):
        """Test memory usage with different payload sizes"""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        article_counts = [1, 5, 10, 20]
        memory_usage = {}
        
        for count in article_counts:
            # Force garbage collection before measurement
            import gc
            gc.collect()
            
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            test_email = self.test_data.generate_performance_test_payload(count)
            payload = {"payload": json.dumps(test_email)}
            
            with patch('boto3.client') as mock_boto_client:
                self._setup_performance_mocks(mock_boto_client, count)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                
                peak_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = peak_memory - initial_memory
                memory_usage[count] = memory_increase
                
                print(f"\n{count} articles - Memory increase: {memory_increase:.2f} MB")
                
                assert response['statusCode'] == 200
        
        # Verify memory usage doesn't grow exponentially
        single_memory = memory_usage[1]
        twenty_memory = memory_usage[20]
        memory_scaling = twenty_memory / single_memory if single_memory > 0 else 1
        
        print(f"\nMemory scaling factor (20 articles vs 1): {memory_scaling:.2f}x")
        assert memory_scaling < 10.0, f"Memory usage scaling too high: {memory_scaling:.2f}x"
    
    def test_error_handling_performance(self):
        """Test performance impact of error handling"""
        test_email = self.test_data.generate_medium_email_with_articles(3)
        payload = {"payload": json.dumps(test_email)}
        
        # Test successful execution time
        success_times = []
        for _ in range(5):
            start_time = time.time()
            
            with patch('boto3.client') as mock_boto_client:
                self._setup_performance_mocks(mock_boto_client, 3)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                execution_time = time.time() - start_time
                success_times.append(execution_time)
                
                assert response['statusCode'] == 200
        
        # Test error execution time
        error_times = []
        for _ in range(5):
            start_time = time.time()
            
            with patch('boto3.client') as mock_boto_client:
                mock_sf_client = MagicMock()
                mock_sf_client.start_sync_execution.return_value = {
                    'status': 'FAILED',
                    'error': 'TestError',
                    'cause': 'Simulated error for performance testing'
                }
                mock_boto_client.return_value = mock_sf_client
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                execution_time = time.time() - start_time
                error_times.append(execution_time)
                
                assert response['statusCode'] == 500
        
        avg_success_time = statistics.mean(success_times)
        avg_error_time = statistics.mean(error_times)
        
        print(f"\nError Handling Performance:")
        print(f"Success average: {avg_success_time:.3f}s")
        print(f"Error average: {avg_error_time:.3f}s")
        print(f"Error overhead: {(avg_error_time / avg_success_time - 1) * 100:.1f}%")
        
        # Error handling shouldn't add significant overhead
        assert avg_error_time < avg_success_time * 1.5, "Error handling adds too much overhead"
    
    def test_stress_testing_large_payloads(self):
        """Test system performance with very large payloads"""
        # Test with progressively larger payloads
        payload_sizes = [20, 50, 100]
        results = {}
        
        for size in payload_sizes:
            test_email = self.test_data.generate_stress_test_payload(size)
            payload = {"payload": json.dumps(test_email)}
            
            # Measure payload size
            payload_size_mb = len(json.dumps(payload)) / (1024 * 1024)
            
            start_time = time.time()
            
            with patch('boto3.client') as mock_boto_client:
                self._setup_performance_mocks(mock_boto_client, size)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                execution_time = time.time() - start_time
                
                results[size] = {
                    'execution_time': execution_time,
                    'payload_size_mb': payload_size_mb,
                    'success': response['statusCode'] == 200
                }
                
                print(f"\nStress Test - {size} articles:")
                print(f"  Payload size: {payload_size_mb:.2f} MB")
                print(f"  Execution time: {execution_time:.3f}s")
                print(f"  Success: {results[size]['success']}")
                
                assert response['statusCode'] == 200
        
        # Verify performance doesn't degrade exponentially
        small_time = results[20]['execution_time']
        large_time = results[100]['execution_time']
        scaling_factor = large_time / small_time
        
        print(f"\nStress test scaling factor (100 vs 20 articles): {scaling_factor:.2f}x")
        assert scaling_factor < 10.0, f"Performance degrades too much with large payloads: {scaling_factor:.2f}x"
    
    def test_edge_case_performance(self):
        """Test performance with various edge cases"""
        edge_cases = self.test_data.generate_edge_case_payloads()
        
        for i, payload in enumerate(edge_cases):
            start_time = time.time()
            
            with patch('boto3.client') as mock_boto_client:
                # Mock appropriate response based on payload validity
                mock_sf_client = MagicMock()
                if not payload.get('payload') or payload.get('payload') == "":
                    # Invalid payload should fail quickly
                    mock_sf_client.start_sync_execution.side_effect = Exception("Invalid payload")
                else:
                    mock_sf_client.start_sync_execution.return_value = {
                        'status': 'SUCCEEDED',
                        'output': json.dumps({'articlesProcessed': 0, 'success': True})
                    }
                
                mock_boto_client.return_value = mock_sf_client
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                try:
                    response = trigger_handler(event, {})
                    execution_time = time.time() - start_time
                    
                    print(f"\nEdge case {i + 1} - Execution time: {execution_time:.3f}s")
                    
                    # Edge cases should be handled quickly (within 2 seconds)
                    assert execution_time < 2.0, f"Edge case {i + 1} took too long: {execution_time:.3f}s"
                    
                except Exception as e:
                    execution_time = time.time() - start_time
                    print(f"\nEdge case {i + 1} - Exception handled in: {execution_time:.3f}s")
                    
                    # Even exceptions should be handled quickly
                    assert execution_time < 1.0, f"Exception handling took too long: {execution_time:.3f}s"
    
    def _setup_performance_mocks(self, mock_boto_client, articles_processed: int):
        """Set up mocks optimized for performance testing"""
        # Mock Step Functions client with minimal delay
        mock_sf_client = MagicMock()
        mock_sf_client.start_sync_execution.return_value = {
            'status': 'SUCCEEDED',
            'output': json.dumps({
                'articlesProcessed': articles_processed,
                'success': True
            })
        }
        
        mock_boto_client.return_value = mock_sf_client
#!/usr/bin/env python3
"""
Performance benchmarking script for Medium Digest Summarizer
Provides detailed performance analysis and benchmarking capabilities
"""

import json
import time
import statistics
import argparse
import sys
import os
from typing import Dict, List, Tuple
from unittest.mock import patch, MagicMock
from tests.test_data_generator import TestDataGenerator


class PerformanceBenchmark:
    """Performance benchmarking suite"""
    
    def __init__(self, profile: str = None):
        self.profile = profile
        if profile:
            os.environ['AWS_PROFILE'] = profile
        
        self.test_data = TestDataGenerator()
        self.results = {}
    
    def benchmark_single_article_processing(self, iterations: int = 10) -> Dict:
        """Benchmark single article processing performance"""
        print(f"🔍 Benchmarking single article processing ({iterations} iterations)")
        
        test_email = self.test_data.generate_medium_email_with_articles(1)
        payload = {"payload": json.dumps(test_email)}
        
        execution_times = []
        memory_usage = []
        
        for i in range(iterations):
            print(f"  Iteration {i + 1}/{iterations}", end="\r")
            
            # Measure memory before
            import psutil
            process = psutil.Process(os.getpid())
            memory_before = process.memory_info().rss / 1024 / 1024  # MB
            
            start_time = time.time()
            
            with patch('boto3.client') as mock_boto_client:
                self._setup_benchmark_mocks(mock_boto_client, 1)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                execution_time = time.time() - start_time
                
                # Measure memory after
                memory_after = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = memory_after - memory_before
                
                execution_times.append(execution_time)
                memory_usage.append(memory_increase)
                
                assert response['statusCode'] == 200
        
        print()  # New line after progress
        
        results = {
            'test_name': 'Single Article Processing',
            'iterations': iterations,
            'execution_times': execution_times,
            'memory_usage': memory_usage,
            'avg_time': statistics.mean(execution_times),
            'median_time': statistics.median(execution_times),
            'min_time': min(execution_times),
            'max_time': max(execution_times),
            'std_dev': statistics.stdev(execution_times) if len(execution_times) > 1 else 0,
            'avg_memory': statistics.mean(memory_usage),
            'max_memory': max(memory_usage)
        }
        
        self._print_benchmark_results(results)
        return results
    
    def benchmark_scaling_performance(self, article_counts: List[int] = None) -> Dict:
        """Benchmark performance scaling with different article counts"""
        if article_counts is None:
            article_counts = [1, 3, 5, 10, 20]
        
        print(f"📈 Benchmarking scaling performance with article counts: {article_counts}")
        
        scaling_results = {}
        
        for count in article_counts:
            print(f"  Testing {count} articles...")
            
            test_email = self.test_data.generate_performance_test_payload(count)
            payload = {"payload": json.dumps(test_email)}
            
            execution_times = []
            
            for _ in range(5):  # 5 iterations per count
                start_time = time.time()
                
                with patch('boto3.client') as mock_boto_client:
                    self._setup_benchmark_mocks(mock_boto_client, count)
                    
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
            scaling_results[count] = {
                'avg_time': avg_time,
                'min_time': min(execution_times),
                'max_time': max(execution_times),
                'std_dev': statistics.stdev(execution_times) if len(execution_times) > 1 else 0
            }
            
            print(f"    Average: {avg_time:.3f}s")
        
        # Calculate scaling factors
        baseline_time = scaling_results[article_counts[0]]['avg_time']
        for count in article_counts:
            scaling_results[count]['scaling_factor'] = scaling_results[count]['avg_time'] / baseline_time
        
        results = {
            'test_name': 'Scaling Performance',
            'article_counts': article_counts,
            'results': scaling_results,
            'baseline_articles': article_counts[0],
            'baseline_time': baseline_time
        }
        
        self._print_scaling_results(results)
        return results
    
    def benchmark_concurrent_performance(self, concurrency_levels: List[int] = None) -> Dict:
        """Benchmark concurrent processing performance"""
        if concurrency_levels is None:
            concurrency_levels = [1, 2, 5, 10]
        
        print(f"🚀 Benchmarking concurrent performance with levels: {concurrency_levels}")
        
        import concurrent.futures
        
        concurrent_results = {}
        
        for concurrency in concurrency_levels:
            print(f"  Testing {concurrency} concurrent requests...")
            
            payloads = self.test_data.generate_concurrent_test_payloads(concurrency)
            
            def make_request(payload):
                start_time = time.time()
                
                with patch('boto3.client') as mock_boto_client:
                    self._setup_benchmark_mocks(mock_boto_client, 2)
                    
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
            
            # Analyze results
            individual_times = []
            success_count = 0
            
            for response, execution_time in request_results:
                individual_times.append(execution_time)
                if response['statusCode'] == 200:
                    success_count += 1
            
            avg_individual_time = statistics.mean(individual_times)
            throughput = concurrency / total_time
            
            concurrent_results[concurrency] = {
                'total_time': total_time,
                'avg_individual_time': avg_individual_time,
                'min_individual_time': min(individual_times),
                'max_individual_time': max(individual_times),
                'throughput': throughput,
                'success_rate': success_count / concurrency,
                'success_count': success_count
            }
            
            print(f"    Total time: {total_time:.3f}s, Throughput: {throughput:.2f} req/s")
        
        results = {
            'test_name': 'Concurrent Performance',
            'concurrency_levels': concurrency_levels,
            'results': concurrent_results
        }
        
        self._print_concurrent_results(results)
        return results
    
    def benchmark_memory_usage(self, payload_sizes: List[int] = None) -> Dict:
        """Benchmark memory usage with different payload sizes"""
        if payload_sizes is None:
            payload_sizes = [1, 5, 10, 20, 50]
        
        print(f"💾 Benchmarking memory usage with payload sizes: {payload_sizes}")
        
        import psutil
        import gc
        
        memory_results = {}
        
        for size in payload_sizes:
            print(f"  Testing {size} articles...")
            
            # Force garbage collection
            gc.collect()
            
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            test_email = self.test_data.generate_performance_test_payload(size)
            payload = {"payload": json.dumps(test_email)}
            payload_size_mb = len(json.dumps(payload)) / (1024 * 1024)
            
            with patch('boto3.client') as mock_boto_client:
                self._setup_benchmark_mocks(mock_boto_client, size)
                
                from lambdas.trigger import lambda_handler as trigger_handler
                
                event = {
                    'body': json.dumps(payload),
                    'headers': {'Content-Type': 'application/json'}
                }
                
                response = trigger_handler(event, {})
                
                peak_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_increase = peak_memory - initial_memory
                
                memory_results[size] = {
                    'payload_size_mb': payload_size_mb,
                    'memory_increase_mb': memory_increase,
                    'peak_memory_mb': peak_memory,
                    'memory_efficiency': payload_size_mb / memory_increase if memory_increase > 0 else 0
                }
                
                print(f"    Payload: {payload_size_mb:.2f}MB, Memory increase: {memory_increase:.2f}MB")
                
                assert response['statusCode'] == 200
        
        results = {
            'test_name': 'Memory Usage',
            'payload_sizes': payload_sizes,
            'results': memory_results
        }
        
        self._print_memory_results(results)
        return results
    
    def run_comprehensive_benchmark(self) -> Dict:
        """Run comprehensive performance benchmark suite"""
        print("🏁 Running comprehensive performance benchmark suite")
        print("=" * 80)
        
        all_results = {}
        
        # Single article processing
        all_results['single_article'] = self.benchmark_single_article_processing()
        
        # Scaling performance
        all_results['scaling'] = self.benchmark_scaling_performance()
        
        # Concurrent performance
        all_results['concurrent'] = self.benchmark_concurrent_performance()
        
        # Memory usage
        all_results['memory'] = self.benchmark_memory_usage()
        
        # Generate summary report
        self._generate_summary_report(all_results)
        
        return all_results
    
    def _setup_benchmark_mocks(self, mock_boto_client, articles_processed: int):
        """Set up mocks optimized for benchmarking"""
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
    
    def _print_benchmark_results(self, results: Dict):
        """Print formatted benchmark results"""
        print(f"\n📊 {results['test_name']} Results:")
        print(f"  Iterations: {results['iterations']}")
        print(f"  Average time: {results['avg_time']:.3f}s")
        print(f"  Median time: {results['median_time']:.3f}s")
        print(f"  Min time: {results['min_time']:.3f}s")
        print(f"  Max time: {results['max_time']:.3f}s")
        print(f"  Std deviation: {results['std_dev']:.3f}s")
        print(f"  Average memory: {results['avg_memory']:.2f}MB")
        print(f"  Max memory: {results['max_memory']:.2f}MB")
    
    def _print_scaling_results(self, results: Dict):
        """Print formatted scaling results"""
        print(f"\n📈 {results['test_name']} Results:")
        print(f"  Baseline: {results['baseline_articles']} articles = {results['baseline_time']:.3f}s")
        print()
        
        for count in results['article_counts']:
            result = results['results'][count]
            print(f"  {count:2d} articles: {result['avg_time']:.3f}s (±{result['std_dev']:.3f}s) "
                  f"[{result['scaling_factor']:.2f}x scaling]")
    
    def _print_concurrent_results(self, results: Dict):
        """Print formatted concurrent results"""
        print(f"\n🚀 {results['test_name']} Results:")
        
        for concurrency in results['concurrency_levels']:
            result = results['results'][concurrency]
            print(f"  {concurrency:2d} concurrent: {result['total_time']:.3f}s total, "
                  f"{result['throughput']:.2f} req/s, {result['success_rate']:.1%} success")
    
    def _print_memory_results(self, results: Dict):
        """Print formatted memory results"""
        print(f"\n💾 {results['test_name']} Results:")
        
        for size in results['payload_sizes']:
            result = results['results'][size]
            print(f"  {size:2d} articles: {result['payload_size_mb']:.2f}MB payload, "
                  f"{result['memory_increase_mb']:.2f}MB increase, "
                  f"{result['memory_efficiency']:.2f} efficiency")
    
    def _generate_summary_report(self, all_results: Dict):
        """Generate comprehensive summary report"""
        print("\n" + "=" * 80)
        print("📋 COMPREHENSIVE BENCHMARK SUMMARY")
        print("=" * 80)
        
        # Single article baseline
        single_result = all_results['single_article']
        print(f"Single Article Baseline: {single_result['avg_time']:.3f}s ±{single_result['std_dev']:.3f}s")
        
        # Scaling analysis
        scaling_result = all_results['scaling']
        worst_scaling = max(
            scaling_result['results'][count]['scaling_factor'] 
            for count in scaling_result['article_counts']
        )
        print(f"Worst Scaling Factor: {worst_scaling:.2f}x")
        
        # Concurrent analysis
        concurrent_result = all_results['concurrent']
        best_throughput = max(
            concurrent_result['results'][level]['throughput']
            for level in concurrent_result['concurrency_levels']
        )
        print(f"Best Throughput: {best_throughput:.2f} requests/second")
        
        # Memory analysis
        memory_result = all_results['memory']
        max_memory_increase = max(
            memory_result['results'][size]['memory_increase_mb']
            for size in memory_result['payload_sizes']
        )
        print(f"Max Memory Increase: {max_memory_increase:.2f}MB")
        
        # Performance recommendations
        print("\n🎯 Performance Recommendations:")
        
        if single_result['avg_time'] > 2.0:
            print("  ⚠️  Single article processing is slow (>2s)")
        else:
            print("  ✅ Single article processing is acceptable")
        
        if worst_scaling > 5.0:
            print("  ⚠️  Scaling performance degrades significantly")
        else:
            print("  ✅ Scaling performance is reasonable")
        
        if best_throughput < 1.0:
            print("  ⚠️  Concurrent throughput is low (<1 req/s)")
        else:
            print("  ✅ Concurrent throughput is acceptable")
        
        if max_memory_increase > 100.0:
            print("  ⚠️  Memory usage is high (>100MB increase)")
        else:
            print("  ✅ Memory usage is reasonable")


def main():
    parser = argparse.ArgumentParser(description='Performance benchmarking for Medium Digest Summarizer')
    
    parser.add_argument('--profile', default='medium-digest',
                       help='AWS profile to use (default: medium-digest)')
    parser.add_argument('--benchmark', choices=['single', 'scaling', 'concurrent', 'memory', 'all'],
                       default='all', help='Benchmark type to run')
    parser.add_argument('--iterations', type=int, default=10,
                       help='Number of iterations for single article benchmark')
    parser.add_argument('--articles', type=int, nargs='+', default=[1, 3, 5, 10, 20],
                       help='Article counts for scaling benchmark')
    parser.add_argument('--concurrency', type=int, nargs='+', default=[1, 2, 5, 10],
                       help='Concurrency levels for concurrent benchmark')
    parser.add_argument('--memory-sizes', type=int, nargs='+', default=[1, 5, 10, 20, 50],
                       help='Payload sizes for memory benchmark')
    
    args = parser.parse_args()
    
    benchmark = PerformanceBenchmark(profile=args.profile)
    
    if args.benchmark == 'single':
        benchmark.benchmark_single_article_processing(args.iterations)
    elif args.benchmark == 'scaling':
        benchmark.benchmark_scaling_performance(args.articles)
    elif args.benchmark == 'concurrent':
        benchmark.benchmark_concurrent_performance(args.concurrency)
    elif args.benchmark == 'memory':
        benchmark.benchmark_memory_usage(args.memory_sizes)
    elif args.benchmark == 'all':
        benchmark.run_comprehensive_benchmark()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Simple load test runner for Medium Digest Summarizer
Executes load and performance tests with configurable parameters
"""

import sys
import argparse
from test_load_and_performance import LoadAndPerformanceTest


def run_concurrent_upload_test(concurrency_levels=None):
    """Run concurrent upload test only"""
    print("🚀 Running concurrent upload test...")
    
    tester = LoadAndPerformanceTest()
    
    try:
        if concurrency_levels:
            results = tester.test_concurrent_s3_uploads(concurrency_levels)
        else:
            results = tester.test_concurrent_s3_uploads()
        
        print("\n✅ Concurrent upload test completed")
        return results
        
    finally:
        tester.cleanup_test_resources()


def run_scaling_test(article_counts=None):
    """Run execution time scaling test only"""
    print("📈 Running execution time scaling test...")
    
    tester = LoadAndPerformanceTest()
    
    try:
        if article_counts:
            results = tester.test_execution_time_scaling(article_counts)
        else:
            results = tester.test_execution_time_scaling()
        
        print("\n✅ Execution time scaling test completed")
        return results
        
    finally:
        tester.cleanup_test_resources()


def run_concurrency_limits_test():
    """Run Step Function concurrency limits test only"""
    print("🔄 Running concurrency limits test...")
    
    tester = LoadAndPerformanceTest()
    
    try:
        results = tester.test_step_function_concurrency_limits()
        print("\n✅ Concurrency limits test completed")
        return results
        
    finally:
        tester.cleanup_test_resources()


def run_high_load_test():
    """Run high load behavior test only"""
    print("🔥 Running high load test...")
    
    tester = LoadAndPerformanceTest()
    
    try:
        results = tester.test_high_load_behavior()
        print("\n✅ High load test completed")
        return results
        
    finally:
        tester.cleanup_test_resources()


def run_quick_test():
    """Run a quick subset of tests for faster feedback"""
    print("⚡ Running quick load test...")
    
    tester = LoadAndPerformanceTest()
    
    try:
        results = {}
        
        # Quick concurrent test (fewer levels)
        print("\n1️⃣ Quick concurrent upload test...")
        concurrent_results = tester.test_concurrent_s3_uploads([2, 5])
        results['concurrent_uploads'] = concurrent_results
        
        # Quick scaling test (fewer article counts)
        print("\n2️⃣ Quick scaling test...")
        scaling_results = tester.test_execution_time_scaling([1, 3, 5])
        results['execution_scaling'] = scaling_results
        
        print("\n✅ Quick load test completed")
        return results
        
    finally:
        tester.cleanup_test_resources()


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(description='Run load and performance tests for Medium Digest Summarizer')
    
    parser.add_argument('--test', choices=['all', 'concurrent', 'scaling', 'concurrency', 'load', 'quick'], 
                       default='quick', help='Type of test to run')
    parser.add_argument('--concurrency-levels', nargs='+', type=int, 
                       help='Concurrency levels to test (e.g., --concurrency-levels 2 5 10)')
    parser.add_argument('--article-counts', nargs='+', type=int,
                       help='Article counts to test (e.g., --article-counts 1 3 5 10)')
    
    args = parser.parse_args()
    
    print("🧪 Medium Digest Summarizer - Load and Performance Testing")
    print("=" * 60)
    
    try:
        if args.test == 'all':
            tester = LoadAndPerformanceTest()
            results = tester.run_all_load_tests()
            
        elif args.test == 'concurrent':
            results = run_concurrent_upload_test(args.concurrency_levels)
            
        elif args.test == 'scaling':
            results = run_scaling_test(args.article_counts)
            
        elif args.test == 'concurrency':
            results = run_concurrency_limits_test()
            
        elif args.test == 'load':
            results = run_high_load_test()
            
        elif args.test == 'quick':
            results = run_quick_test()
        
        # Print basic results summary
        if results and 'error' not in results:
            print(f"\n📊 Test Results Summary:")
            for test_name, result in results.items():
                if isinstance(result, dict) and 'error' not in result:
                    print(f"  ✅ {test_name}: Success")
                else:
                    print(f"  ❌ {test_name}: Failed")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⏹️  Testing interrupted by user")
        return 1
        
    except Exception as e:
        print(f"\n❌ Testing failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
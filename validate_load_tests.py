#!/usr/bin/env python3
"""
Validation script for load and performance testing framework
Tests the framework components without requiring deployed infrastructure
"""

import time
import json
import statistics
import concurrent.futures
from tests.test_data_generator import TestDataGenerator


def test_data_generation_performance():
    """Test performance of test data generation"""
    print("🧪 Testing test data generation performance...")
    
    test_data = TestDataGenerator()
    generation_times = []
    
    # Test different article counts (limited by available sample articles)
    article_counts = [1, 3, 5]
    
    for count in article_counts:
        start_time = time.time()
        
        # Generate multiple emails to get average
        for _ in range(5):
            email = test_data.generate_medium_email_with_articles(count)
            assert len(email['html']) > 0, "Generated email should not be empty"
            actual_links = email['html'].count('medium.com')
            assert actual_links == count, f"Should contain {count} Medium links, found {actual_links}"
        
        generation_time = (time.time() - start_time) / 5  # Average per email
        generation_times.append(generation_time)
        
        print(f"  {count} articles: {generation_time:.4f}s per email")
    
    avg_generation_time = statistics.mean(generation_times)
    print(f"  Average generation time: {avg_generation_time:.4f}s")
    
    # Verify generation is fast enough for load testing
    assert avg_generation_time < 0.1, f"Test data generation too slow: {avg_generation_time:.4f}s"
    
    print("✅ Test data generation performance validated")


def test_concurrent_data_generation():
    """Test concurrent test data generation"""
    print("\n🚀 Testing concurrent test data generation...")
    
    test_data = TestDataGenerator()
    
    def generate_email(article_count):
        """Generate a single email"""
        start_time = time.time()
        email = test_data.generate_medium_email_with_articles(article_count)
        generation_time = time.time() - start_time
        return {
            'email': email,
            'generation_time': generation_time,
            'article_count': article_count,
            'size': len(email['html'])
        }
    
    # Test concurrent generation
    concurrency_levels = [5, 10, 20]
    
    for concurrency in concurrency_levels:
        print(f"  Testing {concurrency} concurrent generations...")
        
        start_time = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            # Generate emails with varying article counts
            article_counts = [1 + (i % 5) for i in range(concurrency)]  # 1-5 articles
            
            futures = [
                executor.submit(generate_email, count)
                for count in article_counts
            ]
            
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        total_time = time.time() - start_time
        
        # Analyze results
        generation_times = [r['generation_time'] for r in results]
        email_sizes = [r['size'] for r in results]
        
        avg_generation_time = statistics.mean(generation_times)
        max_generation_time = max(generation_times)
        avg_email_size = statistics.mean(email_sizes)
        throughput = len(results) / total_time
        
        print(f"    Total time: {total_time:.3f}s")
        print(f"    Average generation time: {avg_generation_time:.4f}s")
        print(f"    Max generation time: {max_generation_time:.4f}s")
        print(f"    Average email size: {avg_email_size:.0f} characters")
        print(f"    Throughput: {throughput:.2f} emails/s")
        
        # Verify concurrent generation is efficient
        assert throughput >= concurrency * 0.5, f"Concurrent throughput too low: {throughput:.2f} emails/s"
        assert max_generation_time < 1.0, f"Max generation time too high: {max_generation_time:.4f}s"
    
    print("✅ Concurrent test data generation validated")


def test_load_test_scenarios():
    """Test different load test scenarios"""
    print("\n📊 Testing load test scenarios...")
    
    test_data = TestDataGenerator()
    
    # Test scenario configurations
    scenarios = [
        {'name': 'Light Load', 'emails': 5, 'articles_per_email': 2},
        {'name': 'Medium Load', 'emails': 10, 'articles_per_email': 3},
        {'name': 'Heavy Load', 'emails': 20, 'articles_per_email': 5},
        {'name': 'Burst Load', 'emails': 50, 'articles_per_email': 1}
    ]
    
    for scenario in scenarios:
        print(f"  Testing {scenario['name']} scenario...")
        
        emails = scenario['emails']
        articles = scenario['articles_per_email']
        
        start_time = time.time()
        
        # Generate test data for scenario
        test_emails = []
        for i in range(emails):
            email = test_data.generate_medium_email_with_articles(articles)
            test_emails.append(email)
        
        generation_time = time.time() - start_time
        
        # Analyze scenario
        total_articles = emails * articles
        total_size = sum(len(email['html']) for email in test_emails)
        avg_email_size = total_size / len(test_emails)
        generation_rate = emails / generation_time
        
        print(f"    Emails: {emails}, Articles per email: {articles}")
        print(f"    Total articles: {total_articles}")
        print(f"    Generation time: {generation_time:.3f}s")
        print(f"    Generation rate: {generation_rate:.2f} emails/s")
        print(f"    Average email size: {avg_email_size:.0f} characters")
        print(f"    Total payload size: {total_size / 1024:.1f} KB")
        
        # Verify scenario generation is reasonable
        assert generation_time < 30, f"Scenario generation too slow: {generation_time:.3f}s"
        assert generation_rate >= 1.0, f"Generation rate too low: {generation_rate:.2f} emails/s"
        assert avg_email_size > 500, f"Email size too small: {avg_email_size:.0f} characters"
    
    print("✅ Load test scenarios validated")


def test_edge_case_handling():
    """Test edge case handling in load tests"""
    print("\n🔍 Testing edge case handling...")
    
    test_data = TestDataGenerator()
    
    # Test edge cases
    edge_cases = [
        {'name': 'No Articles', 'generator': lambda: test_data.generate_medium_email_no_articles()},
        {'name': 'Malformed Email', 'generator': lambda: test_data.generate_malformed_email()},
        {'name': 'Large Email', 'generator': lambda: test_data.generate_stress_test_payload(30)},
    ]
    
    for case in edge_cases:
        print(f"  Testing {case['name']}...")
        
        try:
            start_time = time.time()
            test_email = case['generator']()
            generation_time = time.time() - start_time
            
            # Validate edge case
            assert isinstance(test_email, dict), "Edge case should return dict"
            assert 'html' in test_email, "Edge case should have HTML content"
            assert len(test_email['html']) > 0, "Edge case HTML should not be empty"
            
            print(f"    Generated in {generation_time:.4f}s")
            print(f"    Size: {len(test_email['html'])} characters")
            
            # Verify generation time is reasonable even for edge cases
            assert generation_time < 5.0, f"Edge case generation too slow: {generation_time:.4f}s"
            
        except Exception as e:
            print(f"    ❌ Edge case failed: {e}")
            raise
    
    print("✅ Edge case handling validated")


def test_performance_metrics_calculation():
    """Test performance metrics calculation"""
    print("\n📈 Testing performance metrics calculation...")
    
    # Simulate performance data
    execution_times = [1.2, 1.5, 1.1, 2.3, 1.8, 1.4, 1.6, 1.9, 1.3, 1.7]
    upload_times = [0.1, 0.2, 0.15, 0.12, 0.18, 0.14, 0.16, 0.13, 0.11, 0.17]
    success_counts = [8, 9, 10, 7, 9, 10, 8, 9, 10, 9]
    
    # Calculate metrics
    avg_execution_time = statistics.mean(execution_times)
    median_execution_time = statistics.median(execution_times)
    std_execution_time = statistics.stdev(execution_times)
    
    avg_upload_time = statistics.mean(upload_times)
    max_upload_time = max(upload_times)
    min_upload_time = min(upload_times)
    
    avg_success_rate = statistics.mean(success_counts) / 10.0  # Out of 10
    
    print(f"  Execution time metrics:")
    print(f"    Average: {avg_execution_time:.3f}s")
    print(f"    Median: {median_execution_time:.3f}s")
    print(f"    Std deviation: {std_execution_time:.3f}s")
    
    print(f"  Upload time metrics:")
    print(f"    Average: {avg_upload_time:.3f}s")
    print(f"    Min/Max: {min_upload_time:.3f}s / {max_upload_time:.3f}s")
    
    print(f"  Success rate: {avg_success_rate:.1%}")
    
    # Validate metrics are reasonable
    assert 0.5 < avg_execution_time < 10.0, f"Average execution time unreasonable: {avg_execution_time:.3f}s"
    assert 0.01 < avg_upload_time < 1.0, f"Average upload time unreasonable: {avg_upload_time:.3f}s"
    assert 0.5 < avg_success_rate < 1.0, f"Success rate unreasonable: {avg_success_rate:.1%}"
    
    # Test scaling analysis
    article_counts = [1, 3, 5, 10]
    scaling_times = [1.0, 2.5, 4.2, 7.8]
    
    print(f"  Scaling analysis:")
    for i, (count, time_val) in enumerate(zip(article_counts, scaling_times)):
        if i > 0:
            scaling_factor = time_val / scaling_times[0]
            article_factor = count / article_counts[0]
            efficiency = article_factor / scaling_factor if scaling_factor > 0 else 0
            
            print(f"    {article_counts[0]}→{count} articles: {scaling_factor:.2f}x time, {efficiency:.2f} efficiency")
    
    print("✅ Performance metrics calculation validated")


def test_load_test_framework_integration():
    """Test integration of all load test framework components"""
    print("\n🔧 Testing load test framework integration...")
    
    # Simulate a complete load test workflow
    test_data = TestDataGenerator()
    
    # Phase 1: Generate test data
    print("  Phase 1: Generating test data...")
    test_emails = []
    for i in range(10):
        email = test_data.generate_medium_email_with_articles(2 + (i % 3))
        test_emails.append(email)
    
    assert len(test_emails) == 10, "Should generate 10 test emails"
    
    # Phase 2: Simulate concurrent processing
    print("  Phase 2: Simulating concurrent processing...")
    
    def simulate_processing(email_data):
        """Simulate processing an email"""
        processing_time = 0.1 + (len(email_data['html']) / 10000)  # Simulate variable processing time
        time.sleep(processing_time)
        return {
            'success': True,
            'processing_time': processing_time,
            'articles_found': email_data['html'].count('medium.com'),
            'email_size': len(email_data['html'])
        }
    
    start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(simulate_processing, email) for email in test_emails]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    total_time = time.time() - start_time
    
    # Phase 3: Analyze results
    print("  Phase 3: Analyzing results...")
    
    successful_results = [r for r in results if r['success']]
    processing_times = [r['processing_time'] for r in successful_results]
    articles_found = [r['articles_found'] for r in successful_results]
    
    success_rate = len(successful_results) / len(results)
    avg_processing_time = statistics.mean(processing_times)
    total_articles = sum(articles_found)
    throughput = len(successful_results) / total_time
    
    print(f"    Total emails processed: {len(results)}")
    print(f"    Success rate: {success_rate:.1%}")
    print(f"    Average processing time: {avg_processing_time:.3f}s")
    print(f"    Total articles found: {total_articles}")
    print(f"    Processing throughput: {throughput:.2f} emails/s")
    print(f"    Total test time: {total_time:.3f}s")
    
    # Validate integration results
    assert success_rate >= 0.9, f"Success rate too low: {success_rate:.1%}"
    assert avg_processing_time < 1.0, f"Processing time too high: {avg_processing_time:.3f}s"
    assert throughput >= 2.0, f"Throughput too low: {throughput:.2f} emails/s"
    assert total_articles > 0, "Should find some articles"
    
    print("✅ Load test framework integration validated")


def main():
    """Run all validation tests"""
    print("🧪 Validating Load and Performance Testing Framework")
    print("=" * 60)
    
    try:
        # Run all validation tests
        test_data_generation_performance()
        test_concurrent_data_generation()
        test_load_test_scenarios()
        test_edge_case_handling()
        test_performance_metrics_calculation()
        test_load_test_framework_integration()
        
        print("\n" + "=" * 60)
        print("✅ All validation tests passed!")
        print("🚀 Load and performance testing framework is ready for use")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
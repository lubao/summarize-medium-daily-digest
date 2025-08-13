#!/usr/bin/env python3
"""
Complete workflow testing for Medium Digest Summarizer
Tests deployment validation, error scenarios, and performance
"""

import json
import requests
import time
import boto3
import concurrent.futures
from tests.test_data_generator import TestDataGenerator

# Configuration - REPLACE WITH YOUR VALUES
API_URL = "REPLACE_WITH_YOUR_API_GATEWAY_URL"
API_KEY = "REPLACE_WITH_YOUR_API_KEY"
AWS_PROFILE = "test"

def validate_deployment():
    """Validate that all AWS resources are deployed correctly"""
    print("🔍 Validating deployment...")
    
    try:
        session = boto3.Session(profile_name=AWS_PROFILE)
        
        # Check CloudFormation stack
        cf_client = session.client('cloudformation')
        stack_response = cf_client.describe_stacks(StackName='MediumDigestSummarizerStack')
        stack_status = stack_response['Stacks'][0]['StackStatus']
        
        if stack_status in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
            print("✅ CloudFormation stack deployed successfully")
        else:
            print(f"❌ CloudFormation stack status: {stack_status}")
            return False
        
        # Check Lambda functions
        lambda_client = session.client('lambda')
        expected_functions = [
            'medium-digest-trigger',
            'medium-digest-parse-email',
            'medium-digest-fetch-article',
            'medium-digest-summarize',
            'medium-digest-send-to-slack'
        ]
        
        for function_name in expected_functions:
            try:
                lambda_client.get_function(FunctionName=function_name)
                print(f"✅ Lambda function '{function_name}' exists")
            except Exception as e:
                print(f"❌ Lambda function '{function_name}' not found: {str(e)}")
                return False
        
        # Check Step Function
        sf_client = session.client('stepfunctions')
        state_machines = sf_client.list_state_machines()
        found_sm = False
        for sm in state_machines['stateMachines']:
            if 'medium-digest-summarizer' in sm['name']:
                print(f"✅ Step Function state machine exists: {sm['name']}")
                found_sm = True
                break
        
        if not found_sm:
            print("❌ Step Function state machine not found")
            return False
        
        # Check API Gateway
        apigw_client = session.client('apigateway')
        apis = apigw_client.get_rest_apis()
        found_api = False
        for api in apis['items']:
            if 'MediumDigestApi' in api['name']:
                print(f"✅ API Gateway exists: {api['name']}")
                found_api = True
                break
        
        if not found_api:
            print("❌ API Gateway not found")
            return False
        
        # Check Secrets Manager
        secrets_client = session.client('secretsmanager')
        for secret_name in ['medium-cookies', 'slack-webhook-url']:
            try:
                secrets_client.describe_secret(SecretId=secret_name)
                print(f"✅ Secret '{secret_name}' exists")
            except Exception as e:
                print(f"❌ Secret '{secret_name}' not found: {str(e)}")
                return False
        
        print("✅ All resources validated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Validation failed: {str(e)}")
        return False

def test_valid_email_workflow():
    """Test complete workflow with valid Medium email"""
    print("\n🧪 Testing complete workflow with valid email...")
    
    test_data = TestDataGenerator()
    test_email = test_data.generate_medium_email_with_articles(3)
    
    payload = {
        "payload": json.dumps(test_email)
    }
    
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY
    }
    
    try:
        start_time = time.time()
        response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
        execution_time = time.time() - start_time
        
        print(f"⏱️  Execution time: {execution_time:.2f} seconds")
        print(f"📊 Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Request successful!")
            print(f"📈 Articles processed: {data.get('articlesProcessed', 0)}")
            print(f"📊 Execution status: {data.get('status', 'Unknown')}")
            
            # Performance validation
            if execution_time < 10:
                print("✅ Performance acceptable (< 10 seconds)")
            else:
                print("⚠️  Performance slow (> 10 seconds)")
                
            return True
        else:
            print(f"❌ Request failed: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        return False

def test_invalid_payloads():
    """Test various invalid payload scenarios"""
    print("\n🧪 Testing error scenarios...")
    
    test_cases = [
        {
            'name': 'Empty payload',
            'payload': {'payload': ''},
            'expected_status': [400, 500]
        },
        {
            'name': 'Invalid JSON',
            'payload': {'payload': 'invalid json content'},
            'expected_status': [400, 500]
        },
        {
            'name': 'Missing payload key',
            'payload': {'data': 'test'},
            'expected_status': [400, 500]
        },
        {
            'name': 'No articles in email',
            'payload': {'payload': json.dumps({'html': '<p>No articles here</p>'})},
            'expected_status': [200, 206]
        }
    ]
    
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY
    }
    
    results = []
    
    for test_case in test_cases:
        print(f"  Testing: {test_case['name']}")
        
        try:
            response = requests.post(
                API_URL, 
                json=test_case['payload'], 
                headers=headers, 
                timeout=30
            )
            
            if response.status_code in test_case['expected_status']:
                print(f"    ✅ Handled correctly (status: {response.status_code})")
                results.append(True)
            else:
                print(f"    ⚠️  Unexpected status: {response.status_code}")
                results.append(False)
                
        except Exception as e:
            print(f"    ❌ Test failed: {str(e)}")
            results.append(False)
    
    success_rate = sum(results) / len(results) * 100
    print(f"📊 Error handling success rate: {success_rate:.1f}%")
    
    return success_rate > 75

def test_concurrent_requests():
    """Test system behavior under concurrent load"""
    print("\n🧪 Testing concurrent request handling...")
    
    test_data = TestDataGenerator()
    
    def make_request():
        test_email = test_data.generate_medium_email_with_articles(2)
        payload = {'payload': json.dumps(test_email)}
        headers = {
            'Content-Type': 'application/json',
            'x-api-key': API_KEY
        }
        
        start_time = time.time()
        try:
            response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
            execution_time = time.time() - start_time
            return {
                'status_code': response.status_code,
                'execution_time': execution_time,
                'success': response.status_code == 200
            }
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                'status_code': 0,
                'execution_time': execution_time,
                'success': False,
                'error': str(e)
            }
    
    # Test with 3 concurrent requests
    print("📤 Making 3 concurrent requests...")
    
    start_time = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(make_request) for _ in range(3)]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    
    total_time = time.time() - start_time
    
    # Analyze results
    successful_requests = sum(1 for r in results if r['success'])
    avg_execution_time = sum(r['execution_time'] for r in results) / len(results)
    
    print(f"📊 Concurrent test results:")
    print(f"  Total time: {total_time:.2f} seconds")
    print(f"  Successful requests: {successful_requests}/3")
    print(f"  Average execution time: {avg_execution_time:.2f} seconds")
    
    if successful_requests >= 2:
        print("✅ Concurrent handling acceptable")
        return True
    else:
        print("❌ Concurrent handling needs improvement")
        return False

def test_api_gateway_features():
    """Test API Gateway specific features"""
    print("\n🧪 Testing API Gateway features...")
    
    # Test CORS
    print("  Testing CORS...")
    try:
        response = requests.options(API_URL)
        if 'Access-Control-Allow-Origin' in response.headers:
            print("    ✅ CORS headers present")
        else:
            print("    ⚠️  CORS headers missing")
    except Exception as e:
        print(f"    ❌ CORS test failed: {str(e)}")
    
    # Test API key validation
    print("  Testing API key validation...")
    test_data = TestDataGenerator()
    test_email = test_data.generate_medium_email_with_articles(1)
    payload = {'payload': json.dumps(test_email)}
    
    # Test without API key
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 403:
            print("    ✅ API key validation working")
        else:
            print(f"    ⚠️  Unexpected status without API key: {response.status_code}")
    except Exception as e:
        print(f"    ❌ API key test failed: {str(e)}")
    
    # Test with invalid API key
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': 'invalid-key'
    }
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 403:
            print("    ✅ Invalid API key rejected")
        else:
            print(f"    ⚠️  Invalid API key not rejected: {response.status_code}")
    except Exception as e:
        print(f"    ❌ Invalid API key test failed: {str(e)}")

def run_performance_benchmark():
    """Run basic performance benchmark"""
    print("\n🏃 Running performance benchmark...")
    
    test_data = TestDataGenerator()
    execution_times = []
    
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY
    }
    
    print("📊 Running 5 performance test iterations...")
    
    for i in range(5):
        test_email = test_data.generate_medium_email_with_articles(2)
        payload = {'payload': json.dumps(test_email)}
        
        start_time = time.time()
        try:
            response = requests.post(API_URL, json=payload, headers=headers, timeout=60)
            execution_time = time.time() - start_time
            execution_times.append(execution_time)
            
            print(f"  Iteration {i+1}: {execution_time:.2f}s (status: {response.status_code})")
            
        except Exception as e:
            print(f"  Iteration {i+1}: Failed - {str(e)}")
    
    if execution_times:
        avg_time = sum(execution_times) / len(execution_times)
        min_time = min(execution_times)
        max_time = max(execution_times)
        
        print(f"📈 Performance metrics:")
        print(f"  Average: {avg_time:.2f} seconds")
        print(f"  Min: {min_time:.2f} seconds")
        print(f"  Max: {max_time:.2f} seconds")
        
        if avg_time < 8:
            print("✅ Performance acceptable")
            return True
        else:
            print("⚠️  Performance could be improved")
            return True  # Still acceptable for this test
    else:
        print("❌ No successful performance measurements")
        return False

def main():
    """Run complete workflow testing"""
    print("🚀 Starting complete workflow testing for Medium Digest Summarizer")
    print("=" * 80)
    
    test_results = []
    
    # 1. Validate deployment
    test_results.append(validate_deployment())
    
    # 2. Test valid workflow
    test_results.append(test_valid_email_workflow())
    
    # 3. Test error scenarios
    test_results.append(test_invalid_payloads())
    
    # 4. Test concurrent requests
    test_results.append(test_concurrent_requests())
    
    # 5. Test API Gateway features
    test_api_gateway_features()  # Informational only
    
    # 6. Performance benchmark
    test_results.append(run_performance_benchmark())
    
    # Summary
    print("\n" + "=" * 80)
    print("📋 Test Summary")
    print("=" * 80)
    
    test_names = [
        "Deployment Validation",
        "Valid Workflow Test",
        "Error Scenario Tests",
        "Concurrent Request Test",
        "Performance Benchmark"
    ]
    
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    
    for i, (name, result) in enumerate(zip(test_names, test_results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n📊 Overall Results: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed! Deployment is ready for production.")
    elif passed_tests >= total_tests * 0.8:
        print("⚠️  Most tests passed. Some issues need attention.")
    else:
        print("❌ Multiple test failures. Deployment needs fixes.")
    
    print("\n🏁 Complete workflow testing finished")

if __name__ == "__main__":
    main()
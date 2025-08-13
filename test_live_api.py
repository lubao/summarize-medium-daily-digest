#!/usr/bin/env python3
"""
Live API testing script for Medium Digest Summarizer
Tests the deployed API Gateway endpoint with real requests
"""

import json
import requests
import time
from tests.test_data_generator import TestDataGenerator

# API Configuration - REPLACE WITH YOUR VALUES
API_URL = "REPLACE_WITH_YOUR_API_GATEWAY_URL"
API_KEY = "REPLACE_WITH_YOUR_API_KEY"

def test_api_endpoint():
    """Test the live API endpoint with a sample payload"""
    print("🧪 Testing live API endpoint...")
    
    # Generate test data
    test_data = TestDataGenerator()
    test_email = test_data.generate_medium_email_with_articles(2)
    
    payload = {
        "payload": json.dumps(test_email)
    }
    
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY
    }
    
    print(f"📤 Sending request to: {API_URL}")
    print(f"📦 Payload size: {len(json.dumps(payload))} bytes")
    
    try:
        start_time = time.time()
        response = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=60
        )
        execution_time = time.time() - start_time
        
        print(f"⏱️  Response time: {execution_time:.2f} seconds")
        print(f"📊 Status code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Request successful!")
            print(f"📈 Response data: {json.dumps(data, indent=2)}")
            
            # Validate response structure
            if 'success' in data and data['success']:
                print("✅ Workflow completed successfully")
                if 'articlesProcessed' in data:
                    print(f"📝 Articles processed: {data['articlesProcessed']}")
            else:
                print("⚠️  Workflow completed with issues")
                
        else:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"📄 Response: {response.text}")
            
    except requests.exceptions.Timeout:
        print("⏰ Request timed out after 60 seconds")
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {str(e)}")

def test_invalid_payload():
    """Test API with invalid payload"""
    print("\n🧪 Testing with invalid payload...")
    
    payload = {
        "payload": "invalid payload content"
    }
    
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY
    }
    
    try:
        response = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"📊 Status code: {response.status_code}")
        
        if response.status_code in [400, 500]:
            print("✅ Invalid payload handled correctly")
            data = response.json()
            print(f"📄 Error response: {json.dumps(data, indent=2)}")
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")

def test_api_key_validation():
    """Test API key validation"""
    print("\n🧪 Testing API key validation...")
    
    test_data = TestDataGenerator()
    test_email = test_data.generate_medium_email_with_articles(1)
    
    payload = {
        "payload": json.dumps(test_email)
    }
    
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': 'invalid-api-key'
    }
    
    try:
        response = requests.post(
            API_URL,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"📊 Status code: {response.status_code}")
        
        if response.status_code == 403:
            print("✅ API key validation working correctly")
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")
            print(f"📄 Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")

def test_rate_limiting():
    """Test rate limiting (if applicable)"""
    print("\n🧪 Testing rate limiting...")
    
    test_data = TestDataGenerator()
    test_email = test_data.generate_medium_email_with_articles(1)
    
    payload = {
        "payload": json.dumps(test_email)
    }
    
    headers = {
        'Content-Type': 'application/json',
        'x-api-key': API_KEY
    }
    
    print("📤 Making multiple requests to test rate limiting...")
    
    for i in range(3):
        try:
            response = requests.post(
                API_URL,
                json=payload,
                headers=headers,
                timeout=30
            )
            
            print(f"Request {i+1}: Status {response.status_code}")
            
            if response.status_code == 429:
                print("✅ Rate limiting is working")
                break
                
            time.sleep(1)  # Small delay between requests
            
        except Exception as e:
            print(f"❌ Request {i+1} failed: {str(e)}")

if __name__ == "__main__":
    print("🚀 Starting live API tests for Medium Digest Summarizer")
    print("=" * 60)
    
    # Test 1: Valid payload
    test_api_endpoint()
    
    # Test 2: Invalid payload
    test_invalid_payload()
    
    # Test 3: API key validation
    test_api_key_validation()
    
    # Test 4: Rate limiting
    test_rate_limiting()
    
    print("\n" + "=" * 60)
    print("🏁 Live API tests completed")
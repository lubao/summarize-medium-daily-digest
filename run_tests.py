#!/usr/bin/env python3
"""
Comprehensive test runner for Medium Digest Summarizer
Provides organized test execution with detailed reporting
"""

import argparse
import subprocess
import sys
import time
import os
from typing import Dict, List, Tuple


class TestRunner:
    """Comprehensive test runner with reporting"""
    
    def __init__(self, profile: str = None):
        self.profile = profile
        if profile:
            os.environ['AWS_PROFILE'] = profile
        
        self.test_suites = {
            'unit': {
                'description': 'Unit tests for individual components',
                'command': 'python -m pytest tests/test_*.py -v --tb=short -x --ignore=tests/test_*_integration.py --ignore=tests/test_integration_suite.py --ignore=tests/test_performance.py --ignore=tests/test_deployment_validation.py --ignore=tests/test_end_to_end_integration.py',
                'timeout': 300
            },
            'integration': {
                'description': 'Integration tests for component interactions',
                'command': 'python -m pytest tests/test_*_integration.py -v --tb=short',
                'timeout': 600
            },
            'e2e': {
                'description': 'End-to-end workflow tests',
                'command': 'python -m pytest tests/test_end_to_end_integration.py tests/test_integration_suite.py -v --tb=short',
                'timeout': 900
            },
            'performance': {
                'description': 'Performance and scalability tests',
                'command': 'python -m pytest tests/test_performance.py -v --tb=short -s',
                'timeout': 1200
            },
            'deployment': {
                'description': 'Deployment validation tests',
                'command': 'python -m pytest tests/test_deployment_validation.py -v --tb=short',
                'timeout': 300
            },
            'smoke': {
                'description': 'Quick smoke tests for basic functionality',
                'command': 'python -m pytest tests/test_shared_models.py tests/test_secrets_manager.py tests/test_error_handling.py -v --tb=short -x',
                'timeout': 180
            }
        }
    
    def run_test_suite(self, suite_name: str) -> Tuple[bool, str, float]:
        """Run a specific test suite"""
        if suite_name not in self.test_suites:
            return False, f"Unknown test suite: {suite_name}", 0.0
        
        suite = self.test_suites[suite_name]
        print(f"\n🧪 Running {suite_name} tests: {suite['description']}")
        print(f"Command: {suite['command']}")
        print("-" * 80)
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                suite['command'],
                shell=True,
                check=True,
                capture_output=True,
                text=True,
                timeout=suite['timeout']
            )
            
            execution_time = time.time() - start_time
            
            print(f"✅ {suite_name.title()} tests passed in {execution_time:.2f}s")
            print(f"Output:\n{result.stdout}")
            
            return True, result.stdout, execution_time
            
        except subprocess.CalledProcessError as e:
            execution_time = time.time() - start_time
            
            print(f"❌ {suite_name.title()} tests failed in {execution_time:.2f}s")
            print(f"Error output:\n{e.stderr}")
            print(f"Standard output:\n{e.stdout}")
            
            return False, f"Error: {e.stderr}\nOutput: {e.stdout}", execution_time
            
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            
            print(f"⏰ {suite_name.title()} tests timed out after {execution_time:.2f}s")
            
            return False, f"Tests timed out after {suite['timeout']}s", execution_time
    
    def run_multiple_suites(self, suite_names: List[str]) -> Dict[str, Tuple[bool, str, float]]:
        """Run multiple test suites"""
        results = {}
        total_start_time = time.time()
        
        print(f"🚀 Starting test execution for suites: {', '.join(suite_names)}")
        if self.profile:
            print(f"Using AWS profile: {self.profile}")
        
        for suite_name in suite_names:
            success, output, execution_time = self.run_test_suite(suite_name)
            results[suite_name] = (success, output, execution_time)
        
        total_time = time.time() - total_start_time
        
        # Print summary
        print("\n" + "=" * 80)
        print("TEST EXECUTION SUMMARY")
        print("=" * 80)
        
        passed = 0
        failed = 0
        
        for suite_name, (success, output, execution_time) in results.items():
            status = "✅ PASSED" if success else "❌ FAILED"
            print(f"{suite_name:15} | {status:10} | {execution_time:8.2f}s")
            
            if success:
                passed += 1
            else:
                failed += 1
        
        print("-" * 80)
        print(f"Total suites: {len(suite_names)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Total time: {total_time:.2f}s")
        
        if failed > 0:
            print(f"\n❌ {failed} test suite(s) failed!")
            return results
        else:
            print(f"\n🎉 All {passed} test suite(s) passed!")
            return results
    
    def run_ci_pipeline(self) -> bool:
        """Run CI/CD pipeline test sequence"""
        print("🔄 Running CI/CD pipeline test sequence")
        
        # Define CI pipeline order
        ci_suites = ['smoke', 'unit', 'integration', 'deployment']
        
        results = self.run_multiple_suites(ci_suites)
        
        # Check if all passed
        all_passed = all(success for success, _, _ in results.values())
        
        if all_passed:
            print("\n🎉 CI/CD pipeline completed successfully!")
        else:
            print("\n❌ CI/CD pipeline failed!")
            
        return all_passed
    
    def run_full_test_suite(self) -> bool:
        """Run complete test suite including performance tests"""
        print("🔄 Running full test suite")
        
        # Define full test order
        all_suites = ['smoke', 'unit', 'integration', 'e2e', 'performance', 'deployment']
        
        results = self.run_multiple_suites(all_suites)
        
        # Check if all passed
        all_passed = all(success for success, _, _ in results.values())
        
        if all_passed:
            print("\n🎉 Full test suite completed successfully!")
        else:
            print("\n❌ Full test suite failed!")
            
        return all_passed
    
    def list_available_suites(self):
        """List all available test suites"""
        print("Available test suites:")
        print("-" * 50)
        
        for suite_name, suite_info in self.test_suites.items():
            print(f"{suite_name:15} | {suite_info['description']}")
        
        print("\nSpecial commands:")
        print("ci                | Run CI/CD pipeline (smoke, unit, integration, deployment)")
        print("full              | Run all test suites")


def main():
    parser = argparse.ArgumentParser(description='Comprehensive test runner for Medium Digest Summarizer')
    
    parser.add_argument('suites', nargs='*', 
                       help='Test suites to run (use "list" to see available suites)')
    parser.add_argument('--profile', default='medium-digest',
                       help='AWS profile to use (default: medium-digest)')
    parser.add_argument('--list', action='store_true',
                       help='List available test suites')
    parser.add_argument('--ci', action='store_true',
                       help='Run CI/CD pipeline test sequence')
    parser.add_argument('--full', action='store_true',
                       help='Run full test suite')
    
    args = parser.parse_args()
    
    runner = TestRunner(profile=args.profile)
    
    if args.list or (args.suites and 'list' in args.suites):
        runner.list_available_suites()
        return
    
    if args.ci:
        success = runner.run_ci_pipeline()
        sys.exit(0 if success else 1)
    
    if args.full:
        success = runner.run_full_test_suite()
        sys.exit(0 if success else 1)
    
    if not args.suites:
        print("No test suites specified. Use --list to see available suites.")
        parser.print_help()
        return
    
    # Validate suite names
    invalid_suites = [suite for suite in args.suites if suite not in runner.test_suites]
    if invalid_suites:
        print(f"Invalid test suites: {', '.join(invalid_suites)}")
        print("Use --list to see available suites.")
        sys.exit(1)
    
    # Run specified suites
    results = runner.run_multiple_suites(args.suites)
    
    # Exit with error code if any tests failed
    failed_suites = [suite for suite, (success, _, _) in results.items() if not success]
    if failed_suites:
        sys.exit(1)


if __name__ == "__main__":
    main()
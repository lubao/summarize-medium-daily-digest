#!/usr/bin/env python3
"""
Comprehensive test execution suite for Medium Digest Summarizer
Provides advanced test execution with detailed reporting and analysis
"""

import argparse
import subprocess
import sys
import time
import os
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import concurrent.futures


class AdvancedTestRunner:
    """Advanced test runner with comprehensive reporting and analysis"""
    
    def __init__(self, profile: str = None, parallel: bool = False):
        self.profile = profile
        self.parallel = parallel
        if profile:
            os.environ['AWS_PROFILE'] = profile
        
        self.test_suites = {
            'smoke': {
                'description': 'Quick smoke tests for basic functionality',
                'command': 'python -m pytest tests/test_shared_models.py tests/test_secrets_manager.py tests/test_error_handling.py -v --tb=short -x',
                'timeout': 180,
                'category': 'fast',
                'dependencies': []
            },
            'unit': {
                'description': 'Unit tests for individual components',
                'command': 'python -m pytest tests/test_*.py -v --tb=short -x --ignore=tests/test_*_integration.py --ignore=tests/test_integration_suite.py --ignore=tests/test_performance.py --ignore=tests/test_deployment_validation.py --ignore=tests/test_end_to_end_integration.py --ignore=tests/test_comprehensive_integration.py',
                'timeout': 300,
                'category': 'fast',
                'dependencies': ['smoke']
            },
            'integration': {
                'description': 'Integration tests for component interactions',
                'command': 'python -m pytest tests/test_*_integration.py -v --tb=short',
                'timeout': 600,
                'category': 'medium',
                'dependencies': ['unit']
            },
            'comprehensive': {
                'description': 'Comprehensive integration tests with complex scenarios',
                'command': 'python -m pytest tests/test_comprehensive_integration.py -v --tb=short',
                'timeout': 900,
                'category': 'medium',
                'dependencies': ['integration']
            },
            'e2e': {
                'description': 'End-to-end workflow tests',
                'command': 'python -m pytest tests/test_end_to_end_integration.py tests/test_integration_suite.py -v --tb=short',
                'timeout': 900,
                'category': 'slow',
                'dependencies': ['integration']
            },
            'performance': {
                'description': 'Performance and scalability tests',
                'command': 'python -m pytest tests/test_performance.py -v --tb=short -s',
                'timeout': 1200,
                'category': 'slow',
                'dependencies': ['unit']
            },
            'deployment': {
                'description': 'Deployment validation tests',
                'command': 'python -m pytest tests/test_deployment_validation.py -v --tb=short',
                'timeout': 300,
                'category': 'validation',
                'dependencies': []
            },
            'live': {
                'description': 'Live tests with actual AWS services',
                'command': 'python -m pytest tests/ -v --tb=short --run-live',
                'timeout': 1800,
                'category': 'live',
                'dependencies': ['deployment']
            }
        }
        
        self.execution_results = {}
        self.start_time = None
        self.total_time = 0
    
    def run_test_suite(self, suite_name: str, capture_output: bool = True) -> Tuple[bool, str, float, Dict]:
        """Run a specific test suite with detailed metrics"""
        if suite_name not in self.test_suites:
            return False, f"Unknown test suite: {suite_name}", 0.0, {}
        
        suite = self.test_suites[suite_name]
        print(f"\n🧪 Running {suite_name} tests: {suite['description']}")
        print(f"Command: {suite['command']}")
        print(f"Category: {suite['category']}, Timeout: {suite['timeout']}s")
        print("-" * 80)
        
        start_time = time.time()
        metrics = {
            'start_time': datetime.now().isoformat(),
            'suite_name': suite_name,
            'category': suite['category'],
            'timeout': suite['timeout']
        }
        
        try:
            result = subprocess.run(
                suite['command'],
                shell=True,
                check=True,
                capture_output=capture_output,
                text=True,
                timeout=suite['timeout']
            )
            
            execution_time = time.time() - start_time
            metrics.update({
                'execution_time': execution_time,
                'success': True,
                'return_code': result.returncode,
                'stdout_lines': len(result.stdout.split('\n')) if result.stdout else 0,
                'stderr_lines': len(result.stderr.split('\n')) if result.stderr else 0
            })
            
            # Parse test results from output
            test_stats = self._parse_test_output(result.stdout)
            metrics.update(test_stats)
            
            print(f"✅ {suite_name.title()} tests passed in {execution_time:.2f}s")
            if test_stats:
                print(f"   Tests: {test_stats.get('tests_run', 'N/A')} run, "
                      f"{test_stats.get('tests_passed', 'N/A')} passed, "
                      f"{test_stats.get('tests_failed', 0)} failed")
            
            if not capture_output:
                print(f"Output:\n{result.stdout}")
            
            return True, result.stdout, execution_time, metrics
            
        except subprocess.CalledProcessError as e:
            execution_time = time.time() - start_time
            metrics.update({
                'execution_time': execution_time,
                'success': False,
                'return_code': e.returncode,
                'error': str(e),
                'stdout_lines': len(e.stdout.split('\n')) if e.stdout else 0,
                'stderr_lines': len(e.stderr.split('\n')) if e.stderr else 0
            })
            
            print(f"❌ {suite_name.title()} tests failed in {execution_time:.2f}s")
            print(f"Return code: {e.returncode}")
            if not capture_output:
                print(f"Error output:\n{e.stderr}")
                print(f"Standard output:\n{e.stdout}")
            
            return False, f"Error: {e.stderr}\nOutput: {e.stdout}", execution_time, metrics
            
        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            metrics.update({
                'execution_time': execution_time,
                'success': False,
                'timeout_expired': True,
                'error': f"Timeout after {suite['timeout']}s"
            })
            
            print(f"⏰ {suite_name.title()} tests timed out after {execution_time:.2f}s")
            
            return False, f"Tests timed out after {suite['timeout']}s", execution_time, metrics
    
    def run_multiple_suites(self, suite_names: List[str], 
                           respect_dependencies: bool = True,
                           fail_fast: bool = False) -> Dict[str, Tuple[bool, str, float, Dict]]:
        """Run multiple test suites with dependency management"""
        if respect_dependencies:
            suite_names = self._resolve_dependencies(suite_names)
        
        results = {}
        self.start_time = time.time()
        
        print(f"🚀 Starting test execution for suites: {', '.join(suite_names)}")
        if self.profile:
            print(f"Using AWS profile: {self.profile}")
        print(f"Parallel execution: {'enabled' if self.parallel else 'disabled'}")
        print(f"Fail fast: {'enabled' if fail_fast else 'disabled'}")
        
        if self.parallel and not respect_dependencies:
            # Run suites in parallel
            results = self._run_parallel_suites(suite_names)
        else:
            # Run suites sequentially
            for suite_name in suite_names:
                success, output, execution_time, metrics = self.run_test_suite(suite_name)
                results[suite_name] = (success, output, execution_time, metrics)
                
                if fail_fast and not success:
                    print(f"\n💥 Stopping execution due to failure in {suite_name}")
                    break
        
        self.total_time = time.time() - self.start_time
        self.execution_results = results
        
        # Generate comprehensive report
        self._generate_execution_report(results)
        
        return results
    
    def _run_parallel_suites(self, suite_names: List[str]) -> Dict[str, Tuple[bool, str, float, Dict]]:
        """Run test suites in parallel"""
        results = {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(suite_names), 4)) as executor:
            # Submit all tasks
            future_to_suite = {
                executor.submit(self.run_test_suite, suite_name, True): suite_name 
                for suite_name in suite_names
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_suite):
                suite_name = future_to_suite[future]
                try:
                    success, output, execution_time, metrics = future.result()
                    results[suite_name] = (success, output, execution_time, metrics)
                except Exception as e:
                    print(f"❌ Exception in {suite_name}: {str(e)}")
                    results[suite_name] = (False, str(e), 0.0, {'error': str(e)})
        
        return results
    
    def _resolve_dependencies(self, suite_names: List[str]) -> List[str]:
        """Resolve test suite dependencies and return ordered list"""
        resolved = []
        visited = set()
        
        def visit(suite_name):
            if suite_name in visited:
                return
            visited.add(suite_name)
            
            if suite_name in self.test_suites:
                # Visit dependencies first
                for dep in self.test_suites[suite_name]['dependencies']:
                    if dep in suite_names or dep in [s for s in suite_names if s in self.test_suites]:
                        visit(dep)
                
                if suite_name not in resolved:
                    resolved.append(suite_name)
        
        for suite_name in suite_names:
            visit(suite_name)
        
        return resolved
    
    def _parse_test_output(self, output: str) -> Dict:
        """Parse pytest output to extract test statistics"""
        if not output:
            return {}
        
        stats = {}
        lines = output.split('\n')
        
        # Look for pytest summary line
        for line in lines:
            if 'passed' in line and ('failed' in line or 'error' in line or 'skipped' in line):
                # Parse line like "5 passed, 2 failed, 1 skipped in 10.5s"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'passed' and i > 0:
                        stats['tests_passed'] = int(parts[i-1])
                    elif part == 'failed' and i > 0:
                        stats['tests_failed'] = int(parts[i-1])
                    elif part == 'skipped' and i > 0:
                        stats['tests_skipped'] = int(parts[i-1])
                    elif part == 'error' and i > 0:
                        stats['tests_error'] = int(parts[i-1])
                break
            elif line.strip().endswith('passed'):
                # Simple case: "5 passed in 10.5s"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'passed' and i > 0:
                        stats['tests_passed'] = int(parts[i-1])
                        stats['tests_failed'] = 0
                break
        
        # Calculate total tests
        if 'tests_passed' in stats:
            total = stats['tests_passed']
            total += stats.get('tests_failed', 0)
            total += stats.get('tests_skipped', 0)
            total += stats.get('tests_error', 0)
            stats['tests_run'] = total
        
        return stats
    
    def _generate_execution_report(self, results: Dict):
        """Generate comprehensive execution report"""
        print("\n" + "=" * 80)
        print("📊 COMPREHENSIVE TEST EXECUTION REPORT")
        print("=" * 80)
        
        # Summary statistics
        total_suites = len(results)
        passed_suites = sum(1 for success, _, _, _ in results.values() if success)
        failed_suites = total_suites - passed_suites
        
        total_tests = sum(metrics.get('tests_run', 0) for _, _, _, metrics in results.values())
        total_passed = sum(metrics.get('tests_passed', 0) for _, _, _, metrics in results.values())
        total_failed = sum(metrics.get('tests_failed', 0) for _, _, _, metrics in results.values())
        
        print(f"Execution Time: {self.total_time:.2f}s")
        print(f"Test Suites: {total_suites} total, {passed_suites} passed, {failed_suites} failed")
        print(f"Individual Tests: {total_tests} total, {total_passed} passed, {total_failed} failed")
        print(f"Success Rate: {(passed_suites/total_suites)*100:.1f}% (suites), {(total_passed/total_tests)*100:.1f}% (tests)" if total_tests > 0 else "Success Rate: N/A")
        
        # Detailed results
        print("\n📋 Detailed Results:")
        print("-" * 80)
        print(f"{'Suite':<15} | {'Status':<10} | {'Time':<8} | {'Tests':<12} | {'Category':<10}")
        print("-" * 80)
        
        for suite_name, (success, output, execution_time, metrics) in results.items():
            status = "✅ PASSED" if success else "❌ FAILED"
            tests_info = f"{metrics.get('tests_run', 'N/A'):>3}/{metrics.get('tests_passed', 'N/A'):>3}"
            category = metrics.get('category', 'unknown')
            
            print(f"{suite_name:<15} | {status:<10} | {execution_time:>6.2f}s | {tests_info:<12} | {category:<10}")
        
        # Performance analysis
        print("\n⚡ Performance Analysis:")
        print("-" * 40)
        
        # Categorize by speed
        fast_suites = [(name, time) for name, (_, _, time, metrics) in results.items() 
                      if metrics.get('category') == 'fast']
        medium_suites = [(name, time) for name, (_, _, time, metrics) in results.items() 
                        if metrics.get('category') == 'medium']
        slow_suites = [(name, time) for name, (_, _, time, metrics) in results.items() 
                      if metrics.get('category') == 'slow']
        
        if fast_suites:
            avg_fast = sum(time for _, time in fast_suites) / len(fast_suites)
            print(f"Fast tests average: {avg_fast:.2f}s ({len(fast_suites)} suites)")
        
        if medium_suites:
            avg_medium = sum(time for _, time in medium_suites) / len(medium_suites)
            print(f"Medium tests average: {avg_medium:.2f}s ({len(medium_suites)} suites)")
        
        if slow_suites:
            avg_slow = sum(time for _, time in slow_suites) / len(slow_suites)
            print(f"Slow tests average: {avg_slow:.2f}s ({len(slow_suites)} suites)")
        
        # Identify bottlenecks
        slowest_suite = max(results.items(), key=lambda x: x[1][2])
        print(f"Slowest suite: {slowest_suite[0]} ({slowest_suite[1][2]:.2f}s)")
        
        # Recommendations
        print("\n💡 Recommendations:")
        if failed_suites > 0:
            print(f"  ⚠️  {failed_suites} test suite(s) failed - investigate and fix")
        
        if self.total_time > 600:  # 10 minutes
            print("  ⚠️  Total execution time is high - consider parallel execution")
        
        if any(time > 300 for _, _, time, _ in results.values()):  # 5 minutes
            print("  ⚠️  Some test suites are slow - consider optimization")
        
        if passed_suites == total_suites:
            print("  ✅ All test suites passed - system is healthy")
        
        # Save detailed report to file
        self._save_detailed_report(results)
    
    def _save_detailed_report(self, results: Dict):
        """Save detailed report to JSON file"""
        report_data = {
            'execution_summary': {
                'start_time': self.start_time,
                'total_time': self.total_time,
                'profile': self.profile,
                'parallel': self.parallel,
                'timestamp': datetime.now().isoformat()
            },
            'results': {}
        }
        
        for suite_name, (success, output, execution_time, metrics) in results.items():
            report_data['results'][suite_name] = {
                'success': success,
                'execution_time': execution_time,
                'metrics': metrics,
                'output_preview': output[:500] if output else None  # First 500 chars
            }
        
        filename = f"test-execution-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
            print(f"\n📄 Detailed report saved: {filename}")
        except Exception as e:
            print(f"\n❌ Failed to save detailed report: {str(e)}")
    
    def run_ci_pipeline(self) -> bool:
        """Run optimized CI/CD pipeline"""
        print("🔄 Running optimized CI/CD pipeline")
        
        # CI pipeline with smart ordering
        ci_suites = ['smoke', 'unit', 'integration', 'deployment']
        
        results = self.run_multiple_suites(ci_suites, respect_dependencies=True, fail_fast=True)
        
        # Check if all passed
        all_passed = all(success for success, _, _, _ in results.values())
        
        if all_passed:
            print("\n🎉 CI/CD pipeline completed successfully!")
        else:
            print("\n❌ CI/CD pipeline failed!")
            
        return all_passed
    
    def run_full_test_suite(self) -> bool:
        """Run complete test suite with all categories"""
        print("🔄 Running complete test suite")
        
        # Full test suite
        all_suites = ['smoke', 'unit', 'integration', 'comprehensive', 'e2e', 'performance', 'deployment']
        
        results = self.run_multiple_suites(all_suites, respect_dependencies=True, fail_fast=False)
        
        # Check if all passed
        all_passed = all(success for success, _, _, _ in results.values())
        
        if all_passed:
            print("\n🎉 Complete test suite passed!")
        else:
            print("\n❌ Some tests in the complete suite failed!")
            
        return all_passed
    
    def list_available_suites(self):
        """List all available test suites with details"""
        print("Available test suites:")
        print("-" * 100)
        print(f"{'Suite':<15} | {'Category':<10} | {'Timeout':<8} | {'Dependencies':<15} | {'Description'}")
        print("-" * 100)
        
        for suite_name, suite_info in self.test_suites.items():
            deps = ', '.join(suite_info['dependencies']) if suite_info['dependencies'] else 'None'
            print(f"{suite_name:<15} | {suite_info['category']:<10} | {suite_info['timeout']:<8} | {deps:<15} | {suite_info['description']}")
        
        print("\nSpecial commands:")
        print("ci                | Run optimized CI/CD pipeline")
        print("full              | Run complete test suite")
        print("\nExecution options:")
        print("--parallel        | Run independent suites in parallel")
        print("--fail-fast       | Stop on first failure")
        print("--no-deps         | Ignore dependencies")


def main():
    parser = argparse.ArgumentParser(description='Advanced test execution suite for Medium Digest Summarizer')
    
    parser.add_argument('suites', nargs='*', 
                       help='Test suites to run (use "list" to see available suites)')
    parser.add_argument('--profile', default='medium-digest',
                       help='AWS profile to use (default: medium-digest)')
    parser.add_argument('--list', action='store_true',
                       help='List available test suites')
    parser.add_argument('--ci', action='store_true',
                       help='Run optimized CI/CD pipeline')
    parser.add_argument('--full', action='store_true',
                       help='Run complete test suite')
    parser.add_argument('--parallel', action='store_true',
                       help='Run independent suites in parallel')
    parser.add_argument('--fail-fast', action='store_true',
                       help='Stop execution on first failure')
    parser.add_argument('--no-deps', action='store_true',
                       help='Ignore suite dependencies')
    
    args = parser.parse_args()
    
    runner = AdvancedTestRunner(profile=args.profile, parallel=args.parallel)
    
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
    results = runner.run_multiple_suites(
        args.suites, 
        respect_dependencies=not args.no_deps,
        fail_fast=args.fail_fast
    )
    
    # Exit with error code if any tests failed
    failed_suites = [suite for suite, (success, _, _, _) in results.items() if not success]
    if failed_suites:
        sys.exit(1)


if __name__ == "__main__":
    main()
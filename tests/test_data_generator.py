"""
Test data generator for Medium Digest Summarizer integration tests
Generates sample Medium email payloads and article content for testing
"""

import json
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any


class TestDataGenerator:
    """Generates test data for Medium Digest Summarizer testing"""
    
    def __init__(self):
        self.sample_articles = [
            {
                "title": "The Future of AI in Software Development",
                "url": "https://medium.com/@author1/future-ai-software-development-123abc",
                "content": "Artificial intelligence is revolutionizing how we write, test, and deploy software. From code generation to automated testing, AI tools are becoming indispensable for modern developers. This article explores the current state and future possibilities of AI in software development."
            },
            {
                "title": "Building Scalable Microservices with Python",
                "url": "https://medium.com/@author2/scalable-microservices-python-456def",
                "content": "Microservices architecture has become the gold standard for building scalable applications. This comprehensive guide covers best practices for designing, implementing, and deploying microservices using Python, Docker, and Kubernetes."
            },
            {
                "title": "Understanding AWS Lambda Cold Starts",
                "url": "https://medium.com/@author3/aws-lambda-cold-starts-789ghi",
                "content": "Cold starts in AWS Lambda can significantly impact application performance. This article dives deep into the causes of cold starts, strategies to minimize them, and when to consider alternative architectures for latency-sensitive applications."
            },
            {
                "title": "Data Engineering Best Practices for 2024",
                "url": "https://medium.com/@author4/data-engineering-best-practices-2024-101jkl",
                "content": "The data engineering landscape continues to evolve rapidly. This article outlines the most important best practices for building robust, scalable data pipelines in 2024, including tool selection, monitoring, and data quality management."
            },
            {
                "title": "Securing APIs in the Cloud Era",
                "url": "https://medium.com/@author5/securing-apis-cloud-era-202mno",
                "content": "API security is more critical than ever as organizations move to cloud-native architectures. This guide covers authentication, authorization, rate limiting, and monitoring strategies to protect your APIs from modern threats."
            }
        ]
    
    def generate_medium_email_with_articles(self, num_articles: int = 3) -> Dict[str, Any]:
        """Generate a sample Medium Daily Digest email with specified number of articles"""
        selected_articles = random.sample(self.sample_articles, min(num_articles, len(self.sample_articles)))
        
        # Generate email HTML content
        email_html = self._generate_email_html(selected_articles)
        
        return {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium",
            "date": datetime.now().isoformat(),
            "html": email_html,
            "text": self._generate_email_text(selected_articles)
        }
    
    def generate_medium_email_no_articles(self) -> Dict[str, Any]:
        """Generate a Medium email with no article links"""
        return {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium",
            "date": datetime.now().isoformat(),
            "html": "<html><body><h1>Daily Digest</h1><p>No articles today!</p></body></html>",
            "text": "Daily Digest\nNo articles today!"
        }
    
    def generate_malformed_email(self) -> Dict[str, Any]:
        """Generate a malformed email for error testing"""
        return {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium",
            "date": datetime.now().isoformat(),
            "html": "<html><body><h1>Daily Digest</h1><p>Some content with <a href='not-a-medium-link'>invalid link</a></p></body></html>",
            "text": "Daily Digest\nSome content with invalid link"
        }
    
    def generate_medium_article_html(self, title: str, content: str) -> str:
        """Generate HTML content for a Medium article"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{title}</title>
            <meta property="og:title" content="{title}">
        </head>
        <body>
            <article>
                <header>
                    <h1>{title}</h1>
                    <div class="author">By Test Author</div>
                    <div class="date">{datetime.now().strftime('%B %d, %Y')}</div>
                </header>
                <div class="content">
                    <p>{content}</p>
                    <p>This is additional content to make the article more realistic. 
                    It includes multiple paragraphs and demonstrates how the content 
                    extraction should work in practice.</p>
                </div>
            </article>
            <footer>
                <div class="recommendations">Related articles...</div>
            </footer>
        </body>
        </html>
        """
    
    def generate_concurrent_test_payloads(self, num_payloads: int = 5) -> List[Dict[str, Any]]:
        """Generate multiple payloads for concurrent testing"""
        payloads = []
        for i in range(num_payloads):
            # Vary the number of articles per payload
            num_articles = random.randint(1, 3)
            email_data = self.generate_medium_email_with_articles(num_articles)
            payloads.append({"payload": json.dumps(email_data)})
        return payloads
    
    def generate_stress_test_payload(self, num_articles: int = 50) -> Dict[str, Any]:
        """Generate a very large payload for stress testing"""
        # Create many articles by duplicating and modifying existing ones
        stress_articles = []
        for i in range(num_articles):
            base_article = self.sample_articles[i % len(self.sample_articles)]
            stress_articles.append({
                "title": f"{base_article['title']} - Stress Test Article {i + 1}",
                "url": f"{base_article['url']}-stress-{i + 1}",
                "content": f"{base_article['content']} This is stress test article {i + 1} with extended content to test system limits and performance under heavy load."
            })
        
        email_html = self._generate_email_html(stress_articles)
        
        return {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium - Stress Test",
            "date": datetime.now().isoformat(),
            "html": email_html,
            "text": self._generate_email_text(stress_articles)
        }
    
    def generate_edge_case_payloads(self) -> List[Dict[str, Any]]:
        """Generate various edge case payloads for testing"""
        edge_cases = []
        
        # Empty payload
        edge_cases.append({"payload": ""})
        
        # Invalid JSON
        edge_cases.append({"payload": "invalid json content"})
        
        # Missing payload key
        edge_cases.append({"data": json.dumps(self.generate_medium_email_with_articles(1))})
        
        # Email with very long article titles
        long_title_email = self.generate_medium_email_with_articles(1)
        long_title_email["html"] = long_title_email["html"].replace(
            "The Future of AI in Software Development",
            "The Future of AI in Software Development: A Comprehensive Analysis of Machine Learning, Deep Learning, Natural Language Processing, Computer Vision, and Automated Code Generation Technologies in Modern Software Engineering Practices" * 3
        )
        edge_cases.append({"payload": json.dumps(long_title_email)})
        
        # Email with special characters and Unicode
        unicode_email = {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium - Unicode Test 🚀",
            "date": datetime.now().isoformat(),
            "html": """
            <html><body>
                <h1>Daily Digest 📰</h1>
                <div class="article-item">
                    <h3><a href="https://medium.com/@author/unicode-test-123">Testing Unicode: 中文, العربية, Русский, 日本語 🌍</a></h3>
                    <p>This article contains various Unicode characters and emojis 🎉</p>
                </div>
            </body></html>
            """,
            "text": "Daily Digest 📰\nTesting Unicode: 中文, العربية, Русский, 日本語 🌍"
        }
        edge_cases.append({"payload": json.dumps(unicode_email)})
        
        return edge_cases
    
    def generate_performance_test_payload(self, num_articles: int = 10) -> Dict[str, Any]:
        """Generate a large payload for performance testing"""
        # Create more articles by duplicating and modifying existing ones
        extended_articles = []
        for i in range(num_articles):
            base_article = self.sample_articles[i % len(self.sample_articles)]
            extended_articles.append({
                "title": f"{base_article['title']} - Part {i + 1}",
                "url": f"{base_article['url']}-part-{i + 1}",
                "content": f"{base_article['content']} This is part {i + 1} of the series with additional content for performance testing."
            })
        
        email_html = self._generate_email_html(extended_articles)
        
        return {
            "from": "noreply@medium.com",
            "to": "user@example.com",
            "subject": "Your Daily Digest from Medium - Performance Test",
            "date": datetime.now().isoformat(),
            "html": email_html,
            "text": self._generate_email_text(extended_articles)
        }
    
    def _generate_email_html(self, articles: List[Dict[str, str]]) -> str:
        """Generate HTML content for email with article links"""
        article_links = ""
        for article in articles:
            article_links += f"""
            <div class="article-item">
                <h3><a href="{article['url']}">{article['title']}</a></h3>
                <p>{article['content'][:100]}...</p>
            </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Your Daily Digest from Medium</title>
        </head>
        <body>
            <div class="digest-container">
                <h1>Your Daily Digest</h1>
                <p>Here are today's recommended articles:</p>
                {article_links}
                <footer>
                    <p>Happy reading!</p>
                    <p>The Medium Team</p>
                </footer>
            </div>
        </body>
        </html>
        """
    
    def _generate_email_text(self, articles: List[Dict[str, str]]) -> str:
        """Generate plain text content for email"""
        text_content = "Your Daily Digest\n\nHere are today's recommended articles:\n\n"
        
        for article in articles:
            text_content += f"• {article['title']}\n  {article['url']}\n  {article['content'][:100]}...\n\n"
        
        text_content += "Happy reading!\nThe Medium Team"
        return text_content
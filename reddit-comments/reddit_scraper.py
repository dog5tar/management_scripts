#!/usr/bin/env python3
"""
Reddit comment scraper using requests
This script scrapes comments from Reddit posts using Reddit's public JSON API
without requiring authentication.
"""

import requests
import json
import sys
import os
from datetime import datetime
import time
import argparse
from urllib.parse import urlparse
import re

def scrape_reddit_comments(post_url, output_file):
    """
    Scrape comments from a Reddit post and save to JSON file
    """
    headers = {
        'User-Agent': 'reddit_scraper/1.0 (by /u/temp_user)'
    }
    
    # Convert URL to JSON API URL
    # Remove query parameters and add .json
    base_url = post_url.split('?')[0]
    if not base_url.endswith('.json'):
        json_url = base_url + '.json'
    
    print(f"Fetching data from: {json_url}")
    
    try:
        # Get the post and comments data
        response = requests.get(json_url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        
        # Reddit JSON API returns a list with two elements:
        # [0] = post data, [1] = comments data
        post_data_raw = data[0]['data']['children'][0]['data']
        comments_data_raw = data[1]['data']['children']
        
        comments_data = []
        
        # Extract main post data
        post_data = {
            "type": "submission",
            "id": post_data_raw['id'],
            "title": post_data_raw['title'],
            "author": post_data_raw['author'] if post_data_raw['author'] else "[deleted]",
            "created_utc": post_data_raw['created_utc'],
            "created_date": datetime.fromtimestamp(post_data_raw['created_utc']).isoformat(),
            "score": post_data_raw['score'],
            "upvote_ratio": post_data_raw.get('upvote_ratio', 0),
            "num_comments": post_data_raw['num_comments'],
            "selftext": post_data_raw['selftext'],
            "url": post_data_raw['url'],
            "subreddit": post_data_raw['subreddit'],
            "permalink": f"https://reddit.com{post_data_raw['permalink']}"
        }
        comments_data.append(post_data)
        
        # Extract all comments recursively
        def extract_comments(comment_list, parent_id=None, depth=0):
            for comment_item in comment_list:
                comment = comment_item['data']
                
                # Skip "more" comments objects
                if comment_item['kind'] == 'more':
                    continue
                
                if 'body' in comment:  # Regular comment
                    comment_data = {
                        "type": "comment",
                        "id": comment['id'],
                        "author": comment['author'] if comment['author'] else "[deleted]",
                        "body": comment['body'],
                        "created_utc": comment['created_utc'],
                        "created_date": datetime.fromtimestamp(comment['created_utc']).isoformat(),
                        "score": comment['score'],
                        "parent_id": parent_id,
                        "depth": depth,
                        "permalink": f"https://reddit.com{comment['permalink']}"
                    }
                    comments_data.append(comment_data)
                    
                    # Recursively extract replies
                    if 'replies' in comment and comment['replies'] and comment['replies'] != '':
                        if isinstance(comment['replies'], dict):
                            replies = comment['replies']['data']['children']
                            extract_comments(replies, comment['id'], depth + 1)
        
        # Start extracting comments
        extract_comments(comments_data_raw, post_data_raw['id'])
        
        # Save to JSON file
        with open(output_file, 'w', encoding='utf-8') as f:
            for comment in comments_data:
                json.dump(comment, f, ensure_ascii=False)
                f.write('\n')
        
        print(f"Successfully scraped {len(comments_data)} items (1 post + {len(comments_data)-1} comments)")
        print(f"Data saved to: {output_file}")
        return True
        
    except requests.RequestException as e:
        print(f"Error fetching Reddit data: {e}")
        return False
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error parsing Reddit data: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

def generate_output_filename(url):
    """
    Generate a suitable output filename from a Reddit URL
    """
    # Extract the post ID and title from the URL
    # Reddit URLs typically look like: /r/subreddit/comments/post_id/title/
    match = re.search(r'/comments/([a-zA-Z0-9]+)/([^/]+)', url)
    if match:
        post_id = match.group(1)
        title = match.group(2)
        # Clean the title for use as filename
        clean_title = re.sub(r'[^\w\-_]', '_', title)[:50]  # Limit length
        return f"{clean_title}_{post_id}.json"
    else:
        # Fallback: use timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"reddit_comments_{timestamp}.json"

def read_urls_from_file(file_path):
    """
    Read URLs from a text file (one URL per line)
    """
    urls = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):  # Skip empty lines and comments
                    urls.append(line)
        return urls
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return []
    except Exception as e:
        print(f"Error reading file '{file_path}': {e}")
        return []

def scrape_multiple_urls(urls, output_dir=None, delay=1):
    """
    Scrape comments from multiple Reddit URLs
    """
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    successful = 0
    failed = 0
    
    for i, url in enumerate(urls, 1):
        print(f"\n--- Processing URL {i}/{len(urls)} ---")
        print(f"URL: {url}")
        
        # Generate output filename
        filename = generate_output_filename(url)
        if output_dir:
            output_path = os.path.join(output_dir, filename)
        else:
            output_path = filename
        
        # Scrape the URL
        if scrape_reddit_comments(url, output_path):
            successful += 1
        else:
            failed += 1
            print(f"Failed to scrape: {url}")
        
        # Add delay between requests to be respectful to Reddit's servers
        if i < len(urls):
            print(f"Waiting {delay} seconds before next request...")
            time.sleep(delay)
    
    print(f"\n--- Summary ---")
    print(f"Successfully scraped: {successful}")
    print(f"Failed: {failed}")
    print(f"Total URLs processed: {len(urls)}")

def main():
    parser = argparse.ArgumentParser(description='Scrape comments from Reddit posts')
    parser.add_argument('urls', nargs='*', help='Reddit URLs to scrape')
    parser.add_argument('-f', '--file', help='File containing URLs (one per line)')
    parser.add_argument('-o', '--output-dir', help='Output directory for JSON files')
    parser.add_argument('-d', '--delay', type=float, default=1.0, 
                       help='Delay between requests in seconds (default: 1.0)')
    
    args = parser.parse_args()
    
    urls = []
    
    # Get URLs from command line arguments
    if args.urls:
        urls.extend(args.urls)
    
    # Get URLs from file
    if args.file:
        file_urls = read_urls_from_file(args.file)
        urls.extend(file_urls)
    
    # If no URLs provided, show usage
    if not urls:
        print("No URLs provided. Usage examples:")
        print("1. Command line: python reddit_scraper.py 'https://reddit.com/r/...' 'https://reddit.com/r/...'")
        print("2. From file: python reddit_scraper.py -f urls.txt")
        print("3. Mixed: python reddit_scraper.py -f urls.txt 'https://reddit.com/r/...'")
        print("\nCreate a text file with URLs (one per line) for batch processing.")
        return
    
    print(f"Found {len(urls)} URLs to process")
    scrape_multiple_urls(urls, args.output_dir, args.delay)

if __name__ == "__main__":
    main()

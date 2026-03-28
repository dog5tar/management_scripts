#!/usr/bin/env python3
"""
Podcast Questions Generator from Reddit Comments
This script combines Reddit JSON comment files into a structured PDF
specifically designed to help AI agents generate podcast questions.
"""

import json
import os
import sys
import argparse
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import black, blue, gray, red, green, darkblue
from collections import defaultdict, Counter
import glob
import re

def load_json_comments(file_path):
    """Load comments from a JSON file (one JSON object per line)"""
    comments = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        comment = json.loads(line)
                        comments.append(comment)
                    except json.JSONDecodeError as e:
                        print(f"Warning: Skipping invalid JSON line in {file_path}: {e}")
                        continue
        return comments
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return []

def clean_text_for_pdf(text):
    """Clean text for PDF rendering"""
    if not text:
        return ""
    
    # Replace problematic characters
    replacements = {
        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
        '\u2013': '-', '\u2014': '--', '\u00a0': ' '
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Handle other unicode characters
    text = text.encode('ascii', 'ignore').decode('ascii')
    
    return text

def extract_key_themes(posts_data):
    """Extract key themes and topics from posts for podcast discussion"""
    themes = defaultdict(list)
    career_stages = defaultdict(list)
    pain_points = defaultdict(list)
    
    # Keywords for different categories
    theme_keywords = {
        'Career Transition': ['transition', 'switch', 'move', 'change career', 'pivot'],
        'Leadership': ['cto', 'director', 'manager', 'lead', 'leadership', 'team lead'],
        'Product Management': ['product manager', 'pm', 'product', 'gtm', 'go-to-market'],
        'Startup vs Corporate': ['startup', 'big tech', 'faang', 'corporate', 'small company'],
        'Compensation': ['salary', 'compensation', 'pay', 'money', 'equity', 'stock'],
        'Work-Life Balance': ['wlb', 'work life balance', 'hours', 'stress', 'burnout'],
        'Technical Skills': ['technical', 'coding', 'engineering', 'architecture', 'tech stack']
    }
    
    stage_keywords = {
        'Junior/Mid-level': ['junior', 'entry level', 'new grad', 'early career'],
        'Senior': ['senior', 'staff', 'principal', 'architect'],
        'Management': ['manager', 'director', 'vp', 'cto', 'head of'],
        'Executive': ['c-level', 'executive', 'founder', 'ceo', 'cto']
    }
    
    pain_keywords = {
        'Micromanagement': ['micromanag', 'controlling', 'no autonomy'],
        'Career Growth': ['stuck', 'no growth', 'promotion', 'advancement'],
        'Technical Debt': ['legacy', 'outdated', 'technical debt', 'old tech'],
        'Team Issues': ['team conflict', 'difficult team', 'communication'],
        'Imposter Syndrome': ['imposter', 'not qualified', 'fake it']
    }
    
    for post in posts_data:
        title = post.get('title', '').lower()
        content = post.get('selftext', '').lower()
        full_text = f"{title} {content}"
        
        # Categorize by themes
        for theme, keywords in theme_keywords.items():
            if any(keyword in full_text for keyword in keywords):
                themes[theme].append(post)
        
        # Categorize by career stage
        for stage, keywords in stage_keywords.items():
            if any(keyword in full_text for keyword in keywords):
                career_stages[stage].append(post)
        
        # Identify pain points
        for pain, keywords in pain_keywords.items():
            if any(keyword in full_text for keyword in keywords):
                pain_points[pain].append(post)
    
    return themes, career_stages, pain_points

def extract_controversial_topics(comments_data):
    """Identify controversial topics based on comment patterns"""
    controversial = []
    
    for post_id, comments in comments_data.items():
        if not comments:
            continue
        
        # Look for posts with high engagement but mixed scores
        post_comments = [c for c in comments if c.get('type') == 'comment']
        if len(post_comments) < 5:
            continue
        
        scores = [c.get('score', 0) for c in post_comments if c.get('score', 0) != 0]
        if not scores:
            continue
        
        # Check for polarization (both high positive and negative scores)
        positive_scores = [s for s in scores if s > 5]
        negative_scores = [s for s in scores if s < -2]
        
        if len(positive_scores) > 2 and len(negative_scores) > 1:
            post = next((c for c in comments if c.get('type') == 'submission'), None)
            if post:
                controversial.append({
                    'post': post,
                    'engagement_score': len(post_comments),
                    'polarization': len(positive_scores) + len(negative_scores)
                })
    
    return sorted(controversial, key=lambda x: x['polarization'], reverse=True)

def extract_common_questions(posts_data):
    """Extract common questions and concerns"""
    questions = []
    question_patterns = [
        r'how do i\s+([^?]+)\?',
        r'what.*should i\s+([^?]+)\?',
        r'is it worth\s+([^?]+)\?',
        r'should i\s+([^?]+)\?',
        r'how to\s+([^?]+)\?',
        r'any advice on\s+([^?]+)\?'
    ]
    
    for post in posts_data:
        title = post.get('title', '').lower()
        content = post.get('selftext', '').lower()
        full_text = f"{title} {content}"
        
        for pattern in question_patterns:
            matches = re.findall(pattern, full_text)
            for match in matches:
                questions.append({
                    'question': match.strip(),
                    'post': post,
                    'context': full_text[:200] + '...'
                })
    
    return questions

def create_podcast_pdf(json_files, output_pdf):
    """Create a structured PDF for podcast question generation"""
    doc = SimpleDocTemplate(output_pdf, pagesize=A4, 
                          rightMargin=72, leftMargin=72, 
                          topMargin=72, bottomMargin=18)
    
    # Define styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], 
                                fontSize=18, spaceAfter=12, textColor=darkblue, 
                                fontName='Helvetica-Bold', alignment=1)
    
    section_style = ParagraphStyle('Section', parent=styles['Heading2'], 
                                  fontSize=14, spaceAfter=8, textColor=blue, 
                                  fontName='Helvetica-Bold')
    
    subsection_style = ParagraphStyle('Subsection', parent=styles['Heading3'], 
                                     fontSize=12, spaceAfter=6, textColor=red, 
                                     fontName='Helvetica-Bold')
    
    content_style = ParagraphStyle('Content', parent=styles['Normal'], 
                                  fontSize=10, spaceAfter=6)
    
    highlight_style = ParagraphStyle('Highlight', parent=styles['Normal'], 
                                    fontSize=10, spaceAfter=4, textColor=green, 
                                    fontName='Helvetica-Bold')
    
    # Collect all data
    all_posts = []
    all_comments = defaultdict(list)
    
    for json_file in json_files:
        print(f"Processing: {json_file}")
        comments = load_json_comments(json_file)
        
        post = None
        post_comments = []
        
        for item in comments:
            if item.get('type') == 'submission':
                post = item
                all_posts.append(post)
            elif item.get('type') == 'comment':
                post_comments.append(item)
        
        if post:
            all_comments[post.get('id')] = comments
    
    # Analyze data
    themes, career_stages, pain_points = extract_key_themes(all_posts)
    controversial = extract_controversial_topics(all_comments)
    common_questions = extract_common_questions(all_posts)
    
    # Build PDF content
    story = []
    
    # Title page
    story.append(Paragraph("Podcast Questions Generator", title_style))
    story.append(Paragraph("Reddit Career Discussions Analysis", title_style))
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", content_style))
    story.append(Paragraph(f"Posts Analyzed: {len(all_posts)}", content_style))
    story.append(Paragraph(f"Files Processed: {len(json_files)}", content_style))
    story.append(PageBreak())
    
    # Executive Summary for Podcast Planning
    story.append(Paragraph("EXECUTIVE SUMMARY FOR PODCAST PLANNING", section_style))
    story.append(Paragraph("Key Insights for Interview Questions:", subsection_style))
    
    summary_points = [
        f"• {len(themes)} major themes identified across career discussions",
        f"• {len(controversial)} controversial topics with high engagement",
        f"• {len(common_questions)} common questions and pain points",
        f"• Coverage spans {len(career_stages)} different career stages",
        "• Rich source material for authentic, data-driven interview questions"
    ]
    
    for point in summary_points:
        story.append(Paragraph(point, content_style))
    
    story.append(PageBreak())
    
    # Section 1: Key Themes for Podcast Topics
    story.append(Paragraph("1. MAJOR THEMES FOR PODCAST EPISODES", section_style))
    story.append(Paragraph("These themes represent the most discussed topics and could serve as episode themes:", content_style))
    story.append(Spacer(1, 0.2*inch))
    
    for theme, posts in sorted(themes.items(), key=lambda x: len(x[1]), reverse=True):
        story.append(Paragraph(f"{theme} ({len(posts)} discussions)", subsection_style))
        
        # Sample questions for this theme
        story.append(Paragraph("Suggested Podcast Questions:", highlight_style))
        
        theme_questions = {
            'Career Transition': [
                "What was the biggest challenge you faced when transitioning careers?",
                "How did you know it was time to make a career change?",
                "What advice would you give to someone considering a similar transition?"
            ],
            'Leadership': [
                "What's the difference between being a senior engineer and an engineering manager?",
                "How do you handle the transition from individual contributor to leader?",
                "What are the biggest mistakes new engineering managers make?"
            ],
            'Startup vs Corporate': [
                "How do you decide between a startup CTO role and a director role at a big tech company?",
                "What are the hidden costs of working at a startup vs. big tech?",
                "How does the learning curve differ between startup and corporate environments?"
            ]
        }
        
        questions = theme_questions.get(theme, [
            f"What's your experience with {theme.lower()}?",
            f"What advice would you give about {theme.lower()}?",
            f"What are common misconceptions about {theme.lower()}?"
        ])
        
        for q in questions:
            story.append(Paragraph(f"• {q}", content_style))
        
        # Sample real posts
        story.append(Paragraph("Real Discussion Examples:", highlight_style))
        for i, post in enumerate(posts[:2]):  # Show top 2 examples
            title = clean_text_for_pdf(post.get('title', ''))[:100]
            story.append(Paragraph(f"• \"{title}...\"", content_style))
        
        story.append(Spacer(1, 0.2*inch))
    
    story.append(PageBreak())
    
    # Section 2: Controversial Topics for Engaging Discussions
    story.append(Paragraph("2. CONTROVERSIAL TOPICS FOR ENGAGING INTERVIEWS", section_style))
    story.append(Paragraph("These topics generated heated discussions and could make for compelling podcast content:", content_style))
    story.append(Spacer(1, 0.2*inch))
    
    for i, item in enumerate(controversial[:5], 1):
        post = item['post']
        title = clean_text_for_pdf(post.get('title', ''))
        story.append(Paragraph(f"Controversial Topic #{i}", subsection_style))
        story.append(Paragraph(f"Title: {title}", content_style))
        story.append(Paragraph(f"Engagement Score: {item['engagement_score']} comments", content_style))
        
        story.append(Paragraph("Potential Interview Angles:", highlight_style))
        story.append(Paragraph("• What's your take on this controversial perspective?", content_style))
        story.append(Paragraph("• Have you seen this debate play out in your career?", content_style))
        story.append(Paragraph("• How would you advise someone facing this dilemma?", content_style))
        story.append(Spacer(1, 0.15*inch))
    
    story.append(PageBreak())
    
    # Section 3: Common Questions and Pain Points
    story.append(Paragraph("3. COMMON QUESTIONS & PAIN POINTS", section_style))
    story.append(Paragraph("These represent the most frequent concerns - perfect for FAQ-style segments:", content_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Group similar questions
    question_groups = defaultdict(list)
    for q in common_questions[:20]:  # Top 20 questions
        question_text = q['question']
        if 'transition' in question_text or 'switch' in question_text:
            question_groups['Career Transitions'].append(q)
        elif 'cto' in question_text or 'manager' in question_text:
            question_groups['Leadership Roles'].append(q)
        elif 'salary' in question_text or 'pay' in question_text:
            question_groups['Compensation'].append(q)
        else:
            question_groups['General Career'].append(q)
    
    for group, questions in question_groups.items():
        if questions:
            story.append(Paragraph(f"{group} Questions", subsection_style))
            for q in questions[:5]:  # Top 5 per group
                story.append(Paragraph(f"• {clean_text_for_pdf(q['question'])}", content_style))
            story.append(Spacer(1, 0.15*inch))
    
    story.append(PageBreak())
    
    # Section 4: Career Stage Insights
    story.append(Paragraph("4. CAREER STAGE INSIGHTS FOR TARGETED QUESTIONS", section_style))
    story.append(Paragraph("Tailor your questions based on your guest's career stage:", content_style))
    story.append(Spacer(1, 0.2*inch))
    
    stage_questions = {
        'Junior/Mid-level': [
            "What surprised you most about your first few years in tech?",
            "How do you know when you're ready for the next level?",
            "What skills do you wish you'd developed earlier?"
        ],
        'Senior': [
            "How has the role of senior engineers evolved?",
            "What's the biggest difference between senior and staff level?",
            "How do you balance technical depth with broader impact?"
        ],
        'Management': [
            "What's the hardest part about managing other engineers?",
            "How do you maintain technical credibility as a manager?",
            "What would you do differently if you started managing again?"
        ],
        'Executive': [
            "How do you stay connected to the technical details as an executive?",
            "What's the biggest challenge in scaling engineering organizations?",
            "How do you balance business needs with engineering excellence?"
        ]
    }
    
    for stage, posts in career_stages.items():
        if posts:
            story.append(Paragraph(f"{stage} ({len(posts)} discussions)", subsection_style))
            questions = stage_questions.get(stage, [])
            for q in questions:
                story.append(Paragraph(f"• {q}", content_style))
            story.append(Spacer(1, 0.15*inch))
    
    story.append(PageBreak())
    
    # Section 5: Detailed Post Analysis for Deep Dives
    story.append(Paragraph("5. DETAILED POSTS FOR DEEP DIVE DISCUSSIONS", section_style))
    story.append(Paragraph("High-quality posts that could serve as case studies in interviews:", content_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Select most engaging posts
    engaging_posts = sorted(all_posts, 
                          key=lambda x: x.get('num_comments', 0) + x.get('score', 0), 
                          reverse=True)[:10]
    
    for i, post in enumerate(engaging_posts, 1):
        title = clean_text_for_pdf(post.get('title', ''))
        content = clean_text_for_pdf(post.get('selftext', ''))[:300]
        
        story.append(Paragraph(f"Case Study #{i}", subsection_style))
        story.append(Paragraph(f"Title: {title}", content_style))
        story.append(Paragraph(f"Engagement: {post.get('num_comments', 0)} comments, {post.get('score', 0)} upvotes", content_style))
        
        if content:
            story.append(Paragraph("Summary:", highlight_style))
            story.append(Paragraph(f"{content}...", content_style))
        
        story.append(Paragraph("Interview Questions:", highlight_style))
        story.append(Paragraph("• Have you faced a similar situation in your career?", content_style))
        story.append(Paragraph("• What would be your approach to this challenge?", content_style))
        story.append(Paragraph("• What advice would you give to someone in this position?", content_style))
        story.append(Spacer(1, 0.2*inch))
    
    # Build PDF
    try:
        doc.build(story)
        print(f"Podcast questions PDF created: {output_pdf}")
        return True
    except Exception as e:
        print(f"Error creating PDF: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Generate podcast questions from Reddit career discussions')
    parser.add_argument('-d', '--directory', default='.', 
                       help='Directory containing JSON files (default: current directory)')
    parser.add_argument('-o', '--output', default='podcast_questions_guide.pdf',
                       help='Output PDF filename (default: podcast_questions_guide.pdf)')
    parser.add_argument('-f', '--files', nargs='*',
                       help='Specific JSON files to process')
    
    args = parser.parse_args()
    
    # Get JSON files
    if args.files:
        json_files = args.files
    else:
        pattern = os.path.join(args.directory, "*.json")
        json_files = sorted(glob.glob(pattern))
    
    if not json_files:
        print("No JSON files found to process.")
        return
    
    print(f"Processing {len(json_files)} files for podcast question generation...")
    
    success = create_podcast_pdf(json_files, args.output)
    
    if success:
        print(f"\n✅ Podcast Questions Guide created: {args.output}")
        print("\nThis PDF contains:")
        print("• Key themes for episode planning")
        print("• Controversial topics for engaging discussions") 
        print("• Common questions for FAQ segments")
        print("• Career stage-specific questions")
        print("• Detailed case studies for deep dives")
        print("\nFeed this into your AI agent to generate targeted interview questions!")

if __name__ == "__main__":
    main()
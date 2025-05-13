import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from textblob import TextBlob
import logging
from contextlib import contextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class CommentData:
    post_urn: str
    post_content: str
    comment_text: str
    author_name: str
    author_profile_url: str
    metadata: Dict[str, Any]

@dataclass
class PostData:
    post_urn: str
    content: str
    like_count: int
    comment_count: int
    share_count: int
    author_info: Dict[str, Any]

class DatabaseManager:
    def __init__(self, db_path: str = "linkedin_agent.db"):
        self.db_path = db_path
        self._initialize_database()

    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor with transaction support."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()

    def _initialize_database(self) -> None:
        """Initialize database tables."""
        with self.get_cursor() as cursor:
            # Create comments table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_urn TEXT NOT NULL,
                    post_content TEXT NOT NULL,
                    comment_text TEXT NOT NULL,
                    sentiment_score REAL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    author_name TEXT NOT NULL,
                    author_profile_url TEXT NOT NULL,
                    is_processed BOOLEAN DEFAULT FALSE,
                    response_text TEXT,
                    response_posted BOOLEAN DEFAULT FALSE,
                    metadata TEXT,
                    FOREIGN KEY (post_urn) REFERENCES posts(post_urn)
                )
            """)

            # Create posts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posts (
                    post_urn TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    like_count INTEGER DEFAULT 0,
                    comment_count INTEGER DEFAULT 0,
                    share_count INTEGER DEFAULT 0,
                    author_info TEXT,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def save_comment(self, cursor: sqlite3.Cursor, comment_data: CommentData) -> int:
        """Save a new comment to the database."""
        cursor.execute("""
            INSERT INTO comments (
                post_urn, post_content, comment_text, author_name,
                author_profile_url, metadata
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            comment_data.post_urn,
            comment_data.post_content,
            comment_data.comment_text,
            comment_data.author_name,
            comment_data.author_profile_url,
            json.dumps(comment_data.metadata)
        ))
        return cursor.lastrowid

    def get_unprocessed_comments(self, cursor: sqlite3.Cursor, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieve unprocessed comments from the database."""
        cursor.execute("""
            SELECT id, post_urn, post_content, comment_text, author_name,
                   author_profile_url, metadata
            FROM comments
            WHERE is_processed = FALSE
            LIMIT ?
        """, (limit,))
        
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def mark_as_processed(self, cursor: sqlite3.Cursor, comment_id: int, response_text: Optional[str] = None) -> None:
        """Mark a comment as processed and optionally store the response."""
        cursor.execute("""
            UPDATE comments
            SET is_processed = TRUE,
                response_text = ?,
                response_posted = ?
            WHERE id = ?
        """, (response_text, bool(response_text), comment_id))

    def upsert_post(self, cursor: sqlite3.Cursor, post_data: PostData) -> None:
        """Update or insert a post in the database."""
        cursor.execute("""
            INSERT INTO posts (
                post_urn, content, like_count, comment_count,
                share_count, author_info, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(post_urn) DO UPDATE SET
                content = excluded.content,
                like_count = excluded.like_count,
                comment_count = excluded.comment_count,
                share_count = excluded.share_count,
                author_info = excluded.author_info,
                last_updated = CURRENT_TIMESTAMP
        """, (
            post_data.post_urn,
            post_data.content,
            post_data.like_count,
            post_data.comment_count,
            post_data.share_count,
            json.dumps(post_data.author_info)
        ))

class LinkedInAPI:
    """Mock LinkedIn API client for demonstration purposes."""
    def fetch_new_comments(self, post_urn: str) -> List[CommentData]:
        """Mock method to fetch new comments from LinkedIn."""
        # This would be replaced with actual LinkedIn API calls
        return [
            CommentData(
                post_urn=post_urn,
                post_content="Sample post content",
                comment_text="This is a great post!",
                author_name="John Doe",
                author_profile_url="https://linkedin.com/in/johndoe",
                metadata={"source": "linkedin", "type": "comment"}
            )
        ]

class CommentProcessor:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.linkedin_api = LinkedInAPI()

    def analyze_comment(self, text: str) -> float:
        """Analyze comment sentiment using TextBlob."""
        analysis = TextBlob(text)
        return analysis.sentiment.polarity

    def generate_response(self, comment_data: Dict[str, Any]) -> str:
        """Generate an appropriate response based on comment content and sentiment."""
        sentiment = self.analyze_comment(comment_data['comment_text'])
        
        if sentiment > 0.3:
            return "Thank you for your positive feedback! We're glad you found this helpful."
        elif sentiment < -0.3:
            return "We appreciate your feedback. We're constantly working to improve our content."
        else:
            return "Thank you for your comment! We value your input."

    def process_new_comments(self) -> None:
        """Main processing loop for new comments."""
        with self.db_manager.get_cursor() as cursor:
            # Fetch and save new comments
            for post_urn in self._get_active_posts(cursor):
                comments = self.linkedin_api.fetch_new_comments(post_urn)
                for comment in comments:
                    self.db_manager.save_comment(cursor, comment)

            # Process unprocessed comments
            unprocessed_comments = self.db_manager.get_unprocessed_comments(cursor)
            for comment in unprocessed_comments:
                try:
                    # Analyze sentiment
                    sentiment_score = self.analyze_comment(comment['comment_text'])
                    
                    # Generate response
                    response = self.generate_response(comment)
                    
                    # Update comment status
                    self.db_manager.mark_as_processed(cursor, comment['id'], response)
                    
                    # In a real implementation, we would post the response to LinkedIn here
                    logger.info(f"Processed comment {comment['id']} with response: {response}")
                    
                except Exception as e:
                    logger.error(f"Error processing comment {comment['id']}: {str(e)}")

    def _get_active_posts(self, cursor: sqlite3.Cursor) -> List[str]:
        """Get list of active post URNs from the database."""
        cursor.execute("SELECT post_urn FROM posts")
        return [row[0] for row in cursor.fetchall()]

def main():
    """Main function to demonstrate the LinkedIn Agent functionality."""
    try:
        # Initialize database manager
        db_manager = DatabaseManager()
        
        # Create sample post data
        sample_post = PostData(
            post_urn="urn:li:post:123456",
            content="Sample LinkedIn post content",
            like_count=100,
            comment_count=20,
            share_count=5,
            author_info={"name": "Company Page", "id": "123"}
        )
        
        # Save sample post
        with db_manager.get_cursor() as cursor:
            db_manager.upsert_post(cursor, sample_post)
        
        # Initialize and run comment processor
        processor = CommentProcessor(db_manager)
        processor.process_new_comments()
        
        logger.info("LinkedIn Agent processing completed successfully")
        
    except Exception as e:
        logger.error(f"Error in main execution: {str(e)}")

if __name__ == "__main__":
    main() 
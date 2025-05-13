import pytest
from linkedin_agent import DatabaseManager, CommentData, PostData, CommentProcessor
import os
import json

@pytest.fixture
def db_manager():
    test_db_path = "test_linkedin_agent.db"
    manager = DatabaseManager(db_path=test_db_path)
    yield manager
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

@pytest.fixture
def sample_comment():
    return CommentData(
        post_urn="test:post:123",
        post_content="Test post",
        comment_text="Great post!",
        author_name="Test User",
        author_profile_url="https://linkedin.com/in/test",
        metadata={"source": "test"}
    )

@pytest.fixture
def sample_post():
    return PostData(
        post_urn="test:post:123",
        content="Test post content",
        like_count=10,
        comment_count=5,
        share_count=2,
        author_info={"name": "Test Author"}
    )

def test_save_comment(db_manager, sample_comment):
    with db_manager.get_cursor() as cursor:
        comment_id = db_manager.save_comment(cursor, sample_comment)
        assert comment_id is not None
        
        cursor.execute("SELECT * FROM comments WHERE id = ?", (comment_id,))
        saved_comment = cursor.fetchone()
        assert saved_comment is not None
        assert saved_comment[2] == sample_comment.post_content

def test_get_unprocessed_comments(db_manager, sample_comment):
    with db_manager.get_cursor() as cursor:
        # Save a comment
        db_manager.save_comment(cursor, sample_comment)
        
        # Get unprocessed comments
        unprocessed = db_manager.get_unprocessed_comments(cursor)
        assert len(unprocessed) == 1
        assert unprocessed[0]['comment_text'] == sample_comment.comment_text

def test_mark_as_processed(db_manager, sample_comment):
    with db_manager.get_cursor() as cursor:
        # Save a comment
        comment_id = db_manager.save_comment(cursor, sample_comment)
        
        # Mark as processed
        response = "Thank you for your comment!"
        db_manager.mark_as_processed(cursor, comment_id, response)
        
        # Verify
        cursor.execute("SELECT is_processed, response_text FROM comments WHERE id = ?", (comment_id,))
        result = cursor.fetchone()
        assert result[0] == 1
        assert result[1] == response

def test_upsert_post(db_manager, sample_post):
    with db_manager.get_cursor() as cursor:
        # Insert post
        db_manager.upsert_post(cursor, sample_post)
        
        # Verify
        cursor.execute("SELECT * FROM posts WHERE post_urn = ?", (sample_post.post_urn,))
        saved_post = cursor.fetchone()
        assert saved_post is not None
        assert saved_post[1] == sample_post.content
        
        # Update post
        updated_post = PostData(
            post_urn=sample_post.post_urn,
            content="Updated content",
            like_count=20,
            comment_count=10,
            share_count=5,
            author_info=sample_post.author_info
        )
        db_manager.upsert_post(cursor, updated_post)
        
        # Verify update
        cursor.execute("SELECT content FROM posts WHERE post_urn = ?", (sample_post.post_urn,))
        updated_content = cursor.fetchone()[0]
        assert updated_content == "Updated content"

def test_comment_processor(db_manager):
    processor = CommentProcessor(db_manager)
    
    # Test sentiment analysis
    positive_text = "This is a great post!"
    negative_text = "This is a terrible post!"
    neutral_text = "This is a post."
    
    assert processor.analyze_comment(positive_text) > 0
    assert processor.analyze_comment(negative_text) < 0
    assert abs(processor.analyze_comment(neutral_text)) < 0.3 
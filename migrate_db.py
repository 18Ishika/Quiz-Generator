"""
Database Migration Script
Run this once to add the shuffle_options column to existing database
"""

from app import app, db
from sqlalchemy import text

def migrate_database():
    """Add shuffle_options column to quiz table"""
    with app.app_context():
        try:
            # Check if column already exists
            result = db.session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='quiz' AND column_name='shuffle_options'"
            ))
            
            if result.fetchone():
                print("✓ Column 'shuffle_options' already exists!")
                return
            
            # Add the column
            print("Adding 'shuffle_options' column to quiz table...")
            db.session.execute(text(
                "ALTER TABLE quiz ADD COLUMN shuffle_options BOOLEAN DEFAULT FALSE"
            ))
            db.session.commit()
            print("✓ Column added successfully!")
            
            # Verify the column was added
            result = db.session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='quiz' AND column_name='shuffle_options'"
            ))
            
            if result.fetchone():
                print("✓ Migration completed successfully!")
            else:
                print("✗ Migration failed - column not found after creation")
                
        except Exception as e:
            print(f"✗ Migration failed: {str(e)}")
            db.session.rollback()

if __name__ == "__main__":
    print("=" * 60)
    print("Database Migration - Adding shuffle_options column")
    print("=" * 60)
    migrate_database()
    print("=" * 60)
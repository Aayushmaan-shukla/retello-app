from sqlalchemy import create_engine, text
from app.core.config import settings
import logging

# Set up logging for migration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_db():
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as connection:
        # Check if the name column exists
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='name';
        """))
        name_exists = result.fetchone() is not None

        if name_exists:
            # Add new columns if they don't exist
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS first_name VARCHAR,
                ADD COLUMN IF NOT EXISTS last_name VARCHAR,
                ADD COLUMN IF NOT EXISTS pincode VARCHAR;
            """))

            # Migrate existing name data to first_name
            connection.execute(text("""
                UPDATE users 
                SET first_name = name 
                WHERE first_name IS NULL AND name IS NOT NULL;
            """))

            # Drop the old name column
            connection.execute(text("""
                ALTER TABLE users 
                DROP COLUMN IF EXISTS name;
            """))

        # Check if the gender column exists
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='users' AND column_name='gender';
        """))
        gender_exists = result.fetchone() is not None

        if not gender_exists:
            # Add gender column if it doesn't exist
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS gender VARCHAR;
            """))

        # Check if the button_text column exists in chats table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='chats' AND column_name='button_text';
        """))
        button_text_exists = result.fetchone() is not None

        if not button_text_exists:
            # Add button_text column if it doesn't exist
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN IF NOT EXISTS button_text VARCHAR;
            """))

        # Check if the why_this_phone column exists in chats table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='chats' AND column_name='why_this_phone';
        """))
        why_this_phone_exists = result.fetchone() is not None

        if not why_this_phone_exists:
            # Add why_this_phone column if it doesn't exist
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN IF NOT EXISTS why_this_phone JSON DEFAULT '[]';
            """))

        # Check if the has_more column exists in chats table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='chats' AND column_name='has_more';
        """))
        has_more_exists = result.fetchone() is not None

        if not has_more_exists:
            # Add has_more column if it doesn't exist (completely safe - only adds, never modifies existing data)
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN IF NOT EXISTS has_more BOOLEAN NOT NULL DEFAULT FALSE;
            """))
            
            # OPTIONAL: Update existing records - set has_more based on current_params
            # This preserves existing JSON data while populating the new column
            # Uncomment the next block if you want to migrate existing has_more values
            """
            connection.execute(text('''
                UPDATE chats 
                SET has_more = CASE 
                    WHEN current_params IS NOT NULL 
                         AND JSON_EXTRACT(current_params, '$.has_more') IS NOT NULL 
                    THEN JSON_EXTRACT(current_params, '$.has_more') = 'true'
                    ELSE FALSE 
                END
            '''))
            """
            
            logger.info("Successfully added has_more column to chats table (existing data preserved)")

        connection.commit()

if __name__ == "__main__":
    print("Migrating database...")
    migrate_db()
    print("Database migration completed successfully!") 
from sqlalchemy import create_engine, text
from app.core.config import settings
import logging

# Set up logging for migration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_db():
    """PostgreSQL-specific database migration"""
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.connect() as connection:
        logger.info("Starting PostgreSQL database migration...")
        
        # Check if the name column exists
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='users' AND column_name='name';
        """))
        name_exists = result.fetchone() is not None

        if name_exists:
            logger.info("Migrating name column to first_name and last_name...")
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
            logger.info("Successfully migrated name column")

        # Check if the gender column exists
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='users' AND column_name='gender';
        """))
        gender_exists = result.fetchone() is not None

        if not gender_exists:
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS gender VARCHAR;
            """))
            logger.info("Successfully added gender column to users table")

        # Check if the button_text column exists in chats table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='chats' AND column_name='button_text';
        """))
        button_text_exists = result.fetchone() is not None

        if not button_text_exists:
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN IF NOT EXISTS button_text VARCHAR;
            """))
            logger.info("Successfully added button_text column to chats table")

        # Check if the why_this_phone column exists in chats table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='chats' AND column_name='why_this_phone';
        """))
        why_this_phone_exists = result.fetchone() is not None

        if not why_this_phone_exists:
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN IF NOT EXISTS why_this_phone JSONB DEFAULT '[]'::jsonb;
            """))
            logger.info("Successfully added why_this_phone column to chats table")

        # Check if the has_more column exists in chats table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='chats' AND column_name='has_more';
        """))
        has_more_exists = result.fetchone() is not None

        if not has_more_exists:
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN IF NOT EXISTS has_more BOOLEAN NOT NULL DEFAULT FALSE;
            """))
            logger.info("Successfully added has_more column to chats table")

        # Check if the phones column exists in chats table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='chats' AND column_name='phones';
        """))
        phones_exists = result.fetchone() is not None

        if not phones_exists:
            connection.execute(text("""
                ALTER TABLE chats 
                ADD COLUMN IF NOT EXISTS phones JSONB DEFAULT '[]'::jsonb;
            """))
            logger.info("Successfully added phones column to chats table")

        # Check if the auth_method column exists in users table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='users' AND column_name='auth_method';
        """))
        auth_method_exists = result.fetchone() is not None

        if not auth_method_exists:
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS auth_method VARCHAR DEFAULT 'otp';
            """))
            logger.info("Successfully added auth_method column to users table")

        # Check if the is_email_verified column exists in users table (using snake_case)
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='users' AND column_name='is_email_verified';
        """))
        is_email_verified_exists = result.fetchone() is not None

        if not is_email_verified_exists:
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN NOT NULL DEFAULT FALSE;
            """))
            logger.info("Successfully added is_email_verified column to users table")

        # Check if the email_verification_token column exists in users table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='users' AND column_name='email_verification_token';
        """))
        email_verification_token_exists = result.fetchone() is not None

        if not email_verification_token_exists:
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR;
            """))
            logger.info("Successfully added email_verification_token column to users table")

        # Check if the email_verification_token_expires column exists in users table
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name='users' AND column_name='email_verification_token_expires';
        """))
        email_verification_token_expires_exists = result.fetchone() is not None

        if not email_verification_token_expires_exists:
            connection.execute(text("""
                ALTER TABLE users 
                ADD COLUMN IF NOT EXISTS email_verification_token_expires TIMESTAMPTZ;
            """))
            logger.info("Successfully added email_verification_token_expires column to users table")

        connection.commit()
        logger.info("PostgreSQL database migration completed successfully!")

if __name__ == "__main__":
    print("Migrating PostgreSQL database...")
    migrate_db()
    print("Database migration completed successfully!") 
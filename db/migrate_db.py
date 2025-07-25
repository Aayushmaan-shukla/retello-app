from sqlalchemy import create_engine, text, inspect
from app.core.config import settings
import logging

# Set up logging for migration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_database_type(engine):
    """Check if we're using SQLite or PostgreSQL"""
    return engine.dialect.name

def column_exists(connection, table_name, column_name, db_type):
    """Check if a column exists in a table for both SQLite and PostgreSQL"""
    if db_type == 'sqlite':
        # For SQLite, use PRAGMA table_info
        result = connection.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]  # row[1] is column name
        return column_name in columns
    else:
        # For PostgreSQL, use information_schema
        result = connection.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name=:table_name AND column_name=:column_name;
        """), {"table_name": table_name, "column_name": column_name})
        return result.fetchone() is not None

def migrate_db():
    engine = create_engine(settings.DATABASE_URL)
    db_type = check_database_type(engine)
    logger.info(f"Using database type: {db_type}")
    
    with engine.connect() as connection:
        # Check if the name column exists
        name_exists = column_exists(connection, 'users', 'name', db_type)

        if name_exists:
            # Add new columns if they don't exist
            if not column_exists(connection, 'users', 'first_name', db_type):
                if db_type == 'sqlite':
                    connection.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR"))
                else:
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name VARCHAR"))
            
            if not column_exists(connection, 'users', 'last_name', db_type):
                if db_type == 'sqlite':
                    connection.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR"))
                else:
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR"))
            
            if not column_exists(connection, 'users', 'pincode', db_type):
                if db_type == 'sqlite':
                    connection.execute(text("ALTER TABLE users ADD COLUMN pincode VARCHAR"))
                else:
                    connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS pincode VARCHAR"))

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
        gender_exists = column_exists(connection, 'users', 'gender', db_type)

        if not gender_exists:
            # Add gender column if it doesn't exist
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE users ADD COLUMN gender VARCHAR"))
            else:
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR"))

        # Check if the button_text column exists in chats table
        button_text_exists = column_exists(connection, 'chats', 'button_text', db_type)

        if not button_text_exists:
            # Add button_text column if it doesn't exist
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE chats ADD COLUMN button_text VARCHAR"))
            else:
                connection.execute(text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS button_text VARCHAR"))

        # Check if the why_this_phone column exists in chats table
        why_this_phone_exists = column_exists(connection, 'chats', 'why_this_phone', db_type)

        if not why_this_phone_exists:
            # Add why_this_phone column if it doesn't exist
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE chats ADD COLUMN why_this_phone TEXT DEFAULT '[]'"))
            else:
                connection.execute(text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS why_this_phone JSON DEFAULT '[]'"))

        # Check if the has_more column exists in chats table
        has_more_exists = column_exists(connection, 'chats', 'has_more', db_type)

        if not has_more_exists:
            # Add has_more column if it doesn't exist (completely safe - only adds, never modifies existing data)
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE chats ADD COLUMN has_more BOOLEAN NOT NULL DEFAULT FALSE"))
            else:
                connection.execute(text("ALTER TABLE chats ADD COLUMN IF NOT EXISTS has_more BOOLEAN NOT NULL DEFAULT FALSE"))
            
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

        # Check if the auth_method column exists in users table
        auth_method_exists = column_exists(connection, 'users', 'auth_method', db_type)

        if not auth_method_exists:
            # Add auth_method column if it doesn't exist
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE users ADD COLUMN auth_method VARCHAR DEFAULT 'otp'"))
            else:
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_method VARCHAR DEFAULT 'otp'"))
            
            logger.info("Successfully added auth_method column to users table")

        # Check if the isEmailVerified column exists in users table
        is_email_verified_exists = column_exists(connection, 'users', 'isEmailVerified', db_type)

        if not is_email_verified_exists:
            # Add isEmailVerified column if it doesn't exist
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE users ADD COLUMN isEmailVerified BOOLEAN DEFAULT FALSE"))
            else:
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS isEmailVerified BOOLEAN DEFAULT FALSE"))
            
            logger.info("Successfully added isEmailVerified column to users table")

        # Check if the email_verification_token column exists in users table
        email_verification_token_exists = column_exists(connection, 'users', 'email_verification_token', db_type)

        if not email_verification_token_exists:
            # Add email_verification_token column if it doesn't exist
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE users ADD COLUMN email_verification_token VARCHAR"))
            else:
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token VARCHAR"))
            
            logger.info("Successfully added email_verification_token column to users table")

        # Check if the email_verification_token_expires column exists in users table
        email_verification_token_expires_exists = column_exists(connection, 'users', 'email_verification_token_expires', db_type)

        if not email_verification_token_expires_exists:
            # Add email_verification_token_expires column if it doesn't exist
            if db_type == 'sqlite':
                connection.execute(text("ALTER TABLE users ADD COLUMN email_verification_token_expires DATETIME"))
            else:
                connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verification_token_expires TIMESTAMP"))
            
            logger.info("Successfully added email_verification_token_expires column to users table")

        connection.commit()

if __name__ == "__main__":
    print("Migrating database...")
    migrate_db()
    print("Database migration completed successfully!") 
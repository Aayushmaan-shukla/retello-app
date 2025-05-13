from sqlalchemy import create_engine, text
from app.core.config import settings

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

        connection.commit()

if __name__ == "__main__":
    print("Migrating database...")
    migrate_db()
    print("Database migration completed successfully!") 
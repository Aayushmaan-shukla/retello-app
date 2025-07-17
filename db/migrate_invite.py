"""
SAFE Database migration script for Invite System
This script ONLY ADDS new structures and NEVER deletes existing data
"""

import sys
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# Add the app directory to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_table_exists(session, table_name):
    """Check if a table exists in the database"""
    result = session.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = :table_name
        );
    """), {"table_name": table_name})
    return result.fetchone()[0]

def check_column_exists(session, table_name, column_name):
    """Check if a column exists in a table"""
    result = session.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_name = :table_name AND column_name = :column_name
        );
    """), {"table_name": table_name, "column_name": column_name})
    return result.fetchone()[0]

def check_index_exists(session, index_name):
    """Check if an index exists"""
    result = session.execute(text("""
        SELECT EXISTS (
            SELECT FROM pg_indexes
            WHERE indexname = :index_name
        );
    """), {"index_name": index_name})
    return result.fetchone()[0]

def check_constraint_exists(session, constraint_name):
    """Check if a constraint exists"""
    result = session.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.table_constraints 
            WHERE constraint_name = :constraint_name
        );
    """), {"constraint_name": constraint_name})
    return result.fetchone()[0]

def run_migration():
    """Run the SAFE database migration for invite system - ONLY ADDS, NEVER DELETES"""
    try:
        # Create database engine
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        with SessionLocal() as session:
            logger.info("Starting SAFE Invite System database migration...")
            logger.info("This migration will ONLY ADD new structures and NEVER delete existing data")
            
            # 1. Create invites table ONLY if it doesn't exist
            if not check_table_exists(session, "invites"):
                logger.info("Creating invites table...")
                session.execute(text("""
                    CREATE TABLE invites (
                        id VARCHAR PRIMARY KEY,
                        generated_by VARCHAR NOT NULL,
                        invite_code VARCHAR(12) UNIQUE NOT NULL,
                        max_uses INTEGER NOT NULL DEFAULT 1,
                        current_uses INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NULL,
                        used_at TIMESTAMP NULL,
                        used_by VARCHAR NULL
                    );
                """))
                logger.info("✅ invites table created successfully")
            else:
                logger.info("✅ invites table already exists, skipping creation")
            
            # 2. Create foreign key constraint ONLY if it doesn't exist
            if not check_constraint_exists(session, "fk_invites_generated_by"):
                logger.info("Adding foreign key constraint for generated_by...")
                try:
                    session.execute(text("""
                        ALTER TABLE invites 
                        ADD CONSTRAINT fk_invites_generated_by 
                        FOREIGN KEY (generated_by) REFERENCES users(id) ON DELETE CASCADE;
                    """))
                    logger.info("✅ Foreign key constraint added successfully")
                except Exception as e:
                    logger.warning(f"Could not add foreign key constraint: {e}")
            else:
                logger.info("✅ Foreign key constraint already exists")
            
            # 3. Create indexes ONLY if they don't exist
            logger.info("Creating indexes on invites table...")
            
            # Index on invite_code (unique index will be created automatically)
            if not check_index_exists(session, "idx_invites_invite_code"):
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_invites_invite_code 
                    ON invites(invite_code);
                """))
                logger.info("✅ Index on invite_code created")
            
            # Index on generated_by for faster lookups
            if not check_index_exists(session, "idx_invites_generated_by"):
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_invites_generated_by 
                    ON invites(generated_by);
                """))
                logger.info("✅ Index on generated_by created")
            
            # Index on created_at for ordering
            if not check_index_exists(session, "idx_invites_created_at"):
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_invites_created_at 
                    ON invites(created_at);
                """))
                logger.info("✅ Index on created_at created")
            
            # Index on is_active for filtering
            if not check_index_exists(session, "idx_invites_is_active"):
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_invites_is_active 
                    ON invites(is_active);
                """))
                logger.info("✅ Index on is_active created")
            
            # Composite index for efficient queries
            if not check_index_exists(session, "idx_invites_generated_by_active"):
                session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_invites_generated_by_active 
                    ON invites(generated_by, is_active);
                """))
                logger.info("✅ Composite index on generated_by and is_active created")
            
            # 4. Add any missing columns (for future compatibility)
            if check_table_exists(session, "invites"):
                # Check and add used_by column if it doesn't exist
                if not check_column_exists(session, "invites", "used_by"):
                    logger.info("Adding used_by column to invites table...")
                    session.execute(text("""
                        ALTER TABLE invites ADD COLUMN used_by VARCHAR NULL;
                    """))
                    logger.info("✅ used_by column added successfully")
                
                # Check and add used_at column if it doesn't exist
                if not check_column_exists(session, "invites", "used_at"):
                    logger.info("Adding used_at column to invites table...")
                    session.execute(text("""
                        ALTER TABLE invites ADD COLUMN used_at TIMESTAMP NULL;
                    """))
                    logger.info("✅ used_at column added successfully")
            
            # Commit all changes
            session.commit()
            logger.info("🎉 SAFE Invite System migration completed successfully!")
            logger.info("📊 Summary:")
            logger.info("  - Invites table created/verified")
            logger.info("  - Foreign key constraints added/verified")
            logger.info("  - Indexes created/verified for optimal performance")
            logger.info("  - Additional columns added if needed")
            logger.info("  - NO existing data was deleted or modified")
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}")
        raise

if __name__ == "__main__":
    run_migration() 
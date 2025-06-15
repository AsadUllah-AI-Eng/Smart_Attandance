from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager
from app import app, db
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask-Migrate
migrate = Migrate(app, db)
manager = Manager(app)
manager.add_command('db', MigrateCommand)

# Migration functions
def before_migration(migration_context):
    """Actions to perform before migration"""
    logger.info("Starting database migration...")
    
    # Get current version
    current_revision = migration_context.get_current_revision()
    logger.info(f"Current database version: {current_revision}")
    
    # Backup database before migration
    from database_manager import DatabaseManager
    db_manager = DatabaseManager(app)
    if db_manager.create_backup():
        logger.info("Pre-migration backup created successfully")
    else:
        logger.warning("Failed to create pre-migration backup")

def after_migration(migration_context):
    """Actions to perform after migration"""
    logger.info("Migration completed successfully")
    logger.info(f"New database version: {migration_context.get_current_revision()}")
    
    # Verify database integrity
    try:
        # Check if all tables exist
        for table in db.metadata.tables:
            if not db.engine.dialect.has_table(db.engine, table):
                logger.error(f"Table {table} is missing after migration!")
                return False
        logger.info("Database integrity check passed")
        return True
    except Exception as e:
        logger.error(f"Database integrity check failed: {str(e)}")
        return False

# Register migration hooks
migrate.configure(
    before_migrate=before_migration,
    after_migrate=after_migration
)

if __name__ == '__main__':
    manager.run() 
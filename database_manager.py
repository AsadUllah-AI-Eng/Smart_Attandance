import os
import shutil
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from models import db
from config import Config

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Initialize the database manager with the Flask app"""
        self.app = app
        self.config = app.config
        self._setup_backup_directory()
        
    def _setup_backup_directory(self):
        """Create backup directory if it doesn't exist"""
        os.makedirs(self.config['DB_BACKUP_DIR'], exist_ok=True)
        
    def create_backup(self):
        """Create a backup of the database"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(
                self.config['DB_BACKUP_DIR'],
                f'attendance_backup_{timestamp}.db'
            )
            
            # Create backup
            with self.app.app_context():
                db_file = self.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
                shutil.copy2(db_file, backup_file)
                
            logger.info(f"Database backup created: {backup_file}")
            
            # Clean old backups
            self._cleanup_old_backups()
            return True
            
        except Exception as e:
            logger.error(f"Backup failed: {str(e)}")
            return False
            
    def _cleanup_old_backups(self):
        """Remove backups older than BACKUP_RETENTION_DAYS"""
        retention_days = self.config['BACKUP_RETENTION_DAYS']
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        for backup in os.listdir(self.config['DB_BACKUP_DIR']):
            if not backup.endswith('.db'):
                continue
                
            backup_path = os.path.join(self.config['DB_BACKUP_DIR'], backup)
            file_date = datetime.fromtimestamp(os.path.getctime(backup_path))
            
            if file_date < cutoff_date:
                os.remove(backup_path)
                logger.info(f"Removed old backup: {backup}")
                
    def restore_backup(self, backup_file):
        """Restore database from a backup file"""
        try:
            with self.app.app_context():
                # Stop the Flask app temporarily
                db.session.remove()
                db.engine.dispose()
                
                # Restore the backup
                db_file = self.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
                shutil.copy2(backup_file, db_file)
                
                # Reconnect to the database
                db.engine = create_engine(self.config['SQLALCHEMY_DATABASE_URI'])
                db.session.bind = db.engine
                
                logger.info(f"Database restored from backup: {backup_file}")
                return True
                
        except Exception as e:
            logger.error(f"Restore failed: {str(e)}")
            return False
            
    def optimize_database(self):
        """Perform database optimization tasks"""
        try:
            with self.app.app_context():
                # Vacuum the database to reclaim space
                db.session.execute(text('VACUUM'))
                
                # Analyze tables for query optimization
                db.session.execute(text('ANALYZE'))
                
                # Optimize indexes
                db.session.execute(text('REINDEX'))
                
                db.session.commit()
                logger.info("Database optimization completed successfully")
                return True
                
        except SQLAlchemyError as e:
            logger.error(f"Database optimization failed: {str(e)}")
            return False
            
    def get_database_stats(self):
        """Get database statistics"""
        try:
            with self.app.app_context():
                stats = {
                    'size': self._get_db_size(),
                    'tables': self._get_table_stats(),
                    'last_backup': self._get_last_backup_date()
                }
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {str(e)}")
            return None
            
    def _get_db_size(self):
        """Get the size of the database file"""
        db_file = self.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        return os.path.getsize(db_file)
        
    def _get_table_stats(self):
        """Get statistics for each table"""
        stats = {}
        for table in db.metadata.tables:
            result = db.session.execute(
                text(f'SELECT COUNT(*) FROM {table}')
            ).scalar()
            stats[table] = result
        return stats
        
    def _get_last_backup_date(self):
        """Get the date of the most recent backup"""
        backup_dir = self.config['DB_BACKUP_DIR']
        if not os.path.exists(backup_dir):
            return None
            
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
        if not backups:
            return None
            
        latest_backup = max(
            backups,
            key=lambda x: os.path.getctime(os.path.join(backup_dir, x))
        )
        return datetime.fromtimestamp(
            os.path.getctime(os.path.join(backup_dir, latest_backup))
        )

# Create CLI commands for database management
def register_cli_commands(app):
    @app.cli.command("db-backup")
    def backup_command():
        """Create a database backup."""
        db_manager = DatabaseManager(app)
        if db_manager.create_backup():
            print("Backup created successfully")
        else:
            print("Backup failed")
            
    @app.cli.command("db-optimize")
    def optimize_command():
        """Optimize the database."""
        db_manager = DatabaseManager(app)
        if db_manager.optimize_database():
            print("Database optimization completed")
        else:
            print("Database optimization failed")
            
    @app.cli.command("db-stats")
    def stats_command():
        """Show database statistics."""
        db_manager = DatabaseManager(app)
        stats = db_manager.get_database_stats()
        if stats:
            print("\nDatabase Statistics:")
            print(f"Size: {stats['size'] / 1024:.2f} KB")
            print("\nTable Records:")
            for table, count in stats['tables'].items():
                print(f"- {table}: {count} records")
            if stats['last_backup']:
                print(f"\nLast Backup: {stats['last_backup'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                print("\nNo backups found") 
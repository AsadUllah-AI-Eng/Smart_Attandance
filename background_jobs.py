from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class BackgroundJobManager:
    def __init__(self, app, face_service):
        self.app = app
        self.face_service = face_service
        self.scheduler = BackgroundScheduler()
        self.setup_jobs()
    
    def setup_jobs(self):
        """Setup all background jobs"""
        # Process pending attendance records every minute
        self.scheduler.add_job(
            func=self._process_pending_attendance,
            trigger=IntervalTrigger(minutes=1),
            id='process_pending_attendance',
            name='Process pending attendance records',
            replace_existing=True
        )
        
        # Clean up old captures daily at midnight
        self.scheduler.add_job(
            func=self._cleanup_old_captures,
            trigger='cron',
            hour=0,
            minute=0,
            id='cleanup_old_captures',
            name='Clean up old capture files',
            replace_existing=True
        )
    
    def start(self):
        """Start the scheduler"""
        self.scheduler.start()
        logger.info("Background job scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Background job scheduler stopped")
    
    def _process_pending_attendance(self):
        """Process pending attendance records in background"""
        with self.app.app_context():
            try:
                self.face_service.process_pending_attendance()
                logger.info("Successfully processed pending attendance records")
            except Exception as e:
                logger.error(f"Error processing pending attendance: {str(e)}")
    
    def _cleanup_old_captures(self):
        """Clean up capture files older than 30 days"""
        import os
        from datetime import datetime, timedelta
        
        with self.app.app_context():
            try:
                # Get the cutoff date (30 days ago)
                cutoff_date = datetime.now() - timedelta(days=30)
                
                # Get the captures directory
                captures_dir = os.path.join(self.app.static_folder, 'captures')
                
                # Walk through all course directories
                for course_dir in os.listdir(captures_dir):
                    course_path = os.path.join(captures_dir, course_dir)
                    if not os.path.isdir(course_path):
                        continue
                    
                    # Walk through date directories
                    for date_dir in os.listdir(course_path):
                        try:
                            # Parse the date from directory name
                            dir_date = datetime.strptime(date_dir, '%Y-%m-%d').date()
                            dir_path = os.path.join(course_path, date_dir)
                            
                            # If directory is older than cutoff, delete it
                            if dir_date < cutoff_date.date():
                                import shutil
                                shutil.rmtree(dir_path)
                                logger.info(f"Cleaned up old captures from {dir_path}")
                        except ValueError:
                            # Skip directories that don't match date format
                            continue
                        except Exception as e:
                            logger.error(f"Error cleaning up directory {date_dir}: {str(e)}")
                
                logger.info("Successfully completed capture cleanup")
            except Exception as e:
                logger.error(f"Error during capture cleanup: {str(e)}") 
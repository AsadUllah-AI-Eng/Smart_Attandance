import click
from flask.cli import with_appcontext, current_app
from flask import Flask
from models import Student, Course, Attendance
from datetime import datetime, timedelta
import sqlite3
import os
import json
from tabulate import tabulate
import logging
import shutil

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def register_cli_commands(app):
    """Register all CLI commands with the app"""
    
    # Create a command group for database monitoring
    @app.cli.group()
    def monitor():
        """Database monitoring commands"""
        pass

    @monitor.command()
    @with_appcontext
    def stats():
        """Get database statistics and health metrics"""
        try:
            from app import db
            # Get table counts
            student_count = Student.query.count()
            course_count = Course.query.count()
            attendance_count = Attendance.query.count()
            
            # Get today's attendance stats
            today = datetime.now().date()
            today_attendance = Attendance.query.filter(
                Attendance.date == today
            ).count()
            
            # Get database file size
            db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            db_size = os.path.getsize(db_path) / (1024 * 1024)  # Convert to MB
            
            # Get attendance status distribution
            status_dist = db.session.query(
                Attendance.status,
                db.func.count(Attendance.id)
            ).group_by(Attendance.status).all()
            
            # Print statistics
            click.echo("\n=== Database Statistics ===")
            click.echo(f"Database Size: {db_size:.2f} MB")
            click.echo(f"\nRecord Counts:")
            click.echo(f"- Students: {student_count}")
            click.echo(f"- Courses: {course_count}")
            click.echo(f"- Total Attendance Records: {attendance_count}")
            click.echo(f"- Today's Attendance Records: {today_attendance}")
            
            click.echo("\nAttendance Status Distribution:")
            for status, count in status_dist:
                click.echo(f"- {status}: {count}")
                
        except Exception as e:
            click.echo(f"Error getting database statistics: {str(e)}", err=True)

    @monitor.command()
    @click.option('--days', default=7, help='Number of days to report')
    @with_appcontext
    def report(days):
        """Generate attendance report for a specific period"""
        try:
            from app import db
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # Get attendance data
            attendance_data = db.session.query(
                Course.name.label('course'),
                Student.name.label('student'),
                Attendance.date,
                Attendance.status,
                Attendance.confidence
            ).join(Course).join(Student).filter(
                Attendance.date.between(start_date, end_date)
            ).order_by(Attendance.date.desc()).all()
            
            # Prepare data for tabulate
            headers = ['Date', 'Course', 'Student', 'Status', 'Confidence']
            rows = [[
                record.date.strftime('%Y-%m-%d'),
                record.course,
                record.student,
                record.status.title(),
                f"{record.confidence*100:.1f}%" if record.confidence else 'N/A'
            ] for record in attendance_data]
            
            click.echo(f"\nAttendance Report ({start_date} to {end_date})")
            click.echo(tabulate(rows, headers=headers, tablefmt='grid'))
            
        except Exception as e:
            click.echo(f"Error generating attendance report: {str(e)}", err=True)

    @monitor.command()
    @with_appcontext
    def health():
        """Check database health and integrity"""
        try:
            from app import db
            db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            click.echo("\n=== Database Health Check ===")
            
            # Check database integrity
            cursor.execute("PRAGMA integrity_check")
            integrity = cursor.fetchone()[0]
            click.echo(f"Integrity Check: {integrity}")
            
            # Check for foreign key constraints
            cursor.execute("PRAGMA foreign_key_check")
            fk_violations = cursor.fetchall()
            if fk_violations:
                click.echo("\nForeign Key Violations Found:")
                for violation in fk_violations:
                    click.echo(f"- Table: {violation[0]}, Row ID: {violation[1]}")
            else:
                click.echo("Foreign Key Check: OK")
            
            # Check for orphaned records
            orphaned_attendance = Attendance.query.filter(
                ~Attendance.student_id.in_(
                    db.session.query(Student.id)
                )
            ).count()
            
            if orphaned_attendance:
                click.echo(f"\nOrphaned Records Found:")
                click.echo(f"- Attendance records without valid students: {orphaned_attendance}")
            else:
                click.echo("\nNo orphaned records found")
            
            conn.close()
            
        except Exception as e:
            click.echo(f"Error checking database health: {str(e)}", err=True)

    @monitor.command()
    @with_appcontext
    def backup():
        """Create a backup of the database"""
        try:
            # Create backups directory if it doesn't exist
            backup_dir = os.path.join(current_app.root_path, 'database', 'backups')
            os.makedirs(backup_dir, exist_ok=True)
            
            # Generate backup filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f'attendance_backup_{timestamp}.db')
            
            # Copy database file
            db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
            
            shutil.copy2(db_path, backup_file)
            
            click.echo(f"\nDatabase backup created successfully:")
            click.echo(f"Location: {backup_file}")
            click.echo(f"Size: {os.path.getsize(backup_file) / (1024*1024):.2f} MB")
            
        except Exception as e:
            click.echo(f"Error creating database backup: {str(e)}", err=True) 
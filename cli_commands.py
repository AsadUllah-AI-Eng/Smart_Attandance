import click
from flask.cli import with_appcontext, current_app
from flask import Flask
from models import Student, Course, Attendance
from datetime import datetime

def register_commands(app):
    """Register CLI commands with the app"""
    
    # Custom command group for database operations
    @app.cli.group()
    def database():
        """Database management commands"""
        pass

    # Command to show database statistics
    @database.command()
    @with_appcontext
    def stats():
        """Show database statistics"""
        from app import db
        student_count = Student.query.count()
        course_count = Course.query.count()
        attendance_count = Attendance.query.count()
        
        click.echo("Database Statistics:")
        click.echo(f"Students: {student_count}")
        click.echo(f"Courses: {course_count}")
        click.echo(f"Attendance Records: {attendance_count}")

    # Command to check today's attendance
    @app.cli.command()
    @with_appcontext
    def check_today():
        """Check today's attendance statistics"""
        from app import db
        today = datetime.now().date()
        today_attendance = Attendance.query.filter(
            Attendance.date == today
        ).count()
        
        click.echo(f"Today's Attendance Count: {today_attendance}")

    # Command to list all courses
    @app.cli.command()
    @with_appcontext
    def list_courses():
        """List all available courses"""
        from app import db
        courses = Course.query.all()
        
        if not courses:
            click.echo("No courses found")
            return
            
        click.echo("\nAvailable Courses:")
        for course in courses:
            click.echo(f"- {course.name}") 
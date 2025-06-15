from flask import current_app
from flask_mail import Mail, Message
from typing import List, Dict
import logging
from datetime import datetime
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # Enable detailed logging

class EmailService:
    def __init__(self, app):
        self.app = app
        self.mail = Mail(app)
        self._check_email_config()
    
    def _check_email_config(self):
        """Verify email configuration"""
        logger.info("Checking email configuration...")
        
        # Test SMTP connection
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(current_app.config['MAIL_SERVER'], 
                                current_app.config['MAIL_PORT'],
                                context=context) as server:
                server.login(current_app.config['MAIL_USERNAME'],
                           current_app.config['MAIL_PASSWORD'])
                logger.info("✓ SMTP connection test successful")
                logger.info(f"✓ Connected to {current_app.config['MAIL_SERVER']}:{current_app.config['MAIL_PORT']}")
                logger.info(f"✓ Logged in as {current_app.config['MAIL_USERNAME']}")
        except Exception as e:
            logger.error(f"✗ SMTP connection test failed: {str(e)}")
            logger.error("Please check your email configuration and make sure you're using an App Password if using Gmail.")
    
    def send_attendance_notification(self, student_email: str, student_name: str, course_name: str, status: str, date: str, time: str) -> bool:
        """Send attendance notification email to student"""
        try:
            # Input validation
            if not all([student_email, student_name, course_name, status, date, time]):
                missing_fields = [field for field, value in {
                    'email': student_email, 'name': student_name,
                    'course': course_name, 'status': status,
                    'date': date, 'time': time
                }.items() if not value]
                logger.error(f"Missing required fields: {', '.join(missing_fields)}")
                return False

            if not isinstance(student_email, str) or '@' not in student_email:
                logger.error(f"Invalid email address: {student_email}")
                return False

            # Create message
            msg = MIMEMultipart()
            msg['Subject'] = f"Attendance Marked - {course_name}"
            msg['From'] = current_app.config['MAIL_DEFAULT_SENDER']
            msg['To'] = student_email
            
            # Create message based on status
            if status == 'present':
                body = f"""Dear {student_name},

Your attendance has been marked as PRESENT for the following class:

Course: {course_name}
Date: {date}
Time: {time}

Best regards,
Smart Attendance System"""
            else:  # absent
                body = f"""Dear {student_name},

This is to notify you that you were marked as ABSENT for the following class:

Course: {course_name}
Date: {date}
Time: {time}

If you believe this is an error, please contact your instructor.

Best regards,
Smart Attendance System"""
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email using SSL
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(current_app.config['MAIL_SERVER'], 
                                current_app.config['MAIL_PORT'],
                                context=context) as server:
                server.login(current_app.config['MAIL_USERNAME'],
                           current_app.config['MAIL_PASSWORD'])
                server.send_message(msg)
                
            logger.info(f"✓ Successfully sent attendance notification to {student_email} for {course_name} ({status})")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"✗ SMTP Authentication failed. Please check your email credentials: {str(e)}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"✗ SMTP error sending email to {student_email}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"✗ Unexpected error sending email to {student_email}: {str(e)}")
            return False
    
    def send_bulk_attendance_notifications(self, notifications: List[Dict]) -> bool:
        """Send attendance notifications in bulk"""
        if not notifications:
            logger.warning("No notifications to send")
            return True

        success_count = 0
        failure_count = 0
        
        try:
            # Create SSL context once for all emails
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(current_app.config['MAIL_SERVER'], 
                                current_app.config['MAIL_PORT'],
                                context=context) as server:
                server.login(current_app.config['MAIL_USERNAME'],
                           current_app.config['MAIL_PASSWORD'])
                
                for notification in notifications:
                    try:
                        result = self.send_attendance_notification(
                            student_email=notification['email'],
                            student_name=notification['name'],
                            course_name=notification['course'],
                            status=notification['status'],
                            date=notification['date'],
                            time=notification['time']
                        )
                        if result:
                            success_count += 1
                        else:
                            failure_count += 1
                    except Exception as e:
                        logger.error(f"✗ Error sending notification to {notification.get('email', 'unknown')}: {str(e)}")
                        failure_count += 1
                        continue
            
            total = len(notifications)
            logger.info(f"Bulk notification complete: {success_count}/{total} successful, {failure_count}/{total} failed")
            return failure_count == 0
            
        except Exception as e:
            logger.error(f"✗ Error in bulk notification process: {str(e)}")
            return False
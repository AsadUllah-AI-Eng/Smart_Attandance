import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Email configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = "syco6377@gmail.com"  # Replace with your Gmail
SENDER_PASSWORD = "zprchyrqwyhuisgr"   # Replace with your App Password
TEST_RECIPIENT = "syco6377@gmail.com" # Replace with your email to test

def test_email():
    print("Starting email test...")
    
    try:
        # Create message
        msg = MIMEMultipart()
        msg['Subject'] = 'Test Email - Smart Attendance System'
        msg['From'] = SENDER_EMAIL
        msg['To'] = TEST_RECIPIENT
        
        body = """
        This is a test email from Smart Attendance System.
        
        If you receive this email, your email configuration is working correctly.
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        print(f"Connecting to {SMTP_SERVER}:{SMTP_PORT}...")
        
        # Create secure SSL context
        context = ssl.create_default_context()
        
        # Connect to server
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            print(f"Logging in as {SENDER_EMAIL}...")
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            
            print("Sending test email...")
            server.send_message(msg)
            
        print("✓ Test email sent successfully!")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"✗ Authentication failed: {str(e)}")
        print("Please check your email and App Password")
        return False
        
    except Exception as e:
        print(f"✗ Error sending email: {str(e)}")
        return False

if __name__ == "__main__":
    test_email() 
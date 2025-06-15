from app import app, db
from models import Attendance
import os

def clear_attendance():
    try:
        with app.app_context():
            # Delete all attendance records
            Attendance.query.delete()
            db.session.commit()
            print("Successfully cleared all attendance records.")

            # Optionally clear captured images
            captures_dir = os.path.join('static', 'captures')
            if os.path.exists(captures_dir):
                for root, dirs, files in os.walk(captures_dir, topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
                print("Successfully cleared captured images.")

    except Exception as e:
        print(f"Error clearing attendance: {str(e)}")

if __name__ == "__main__":
    clear_attendance() 
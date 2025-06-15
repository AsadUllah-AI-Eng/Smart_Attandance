 HEAD
# Smart-attandance
Automatic Atteendance systen using facial recognition

# Smart_Attandance

An AI-powered face recognition system for automated classroom attendance tracking.

## Features

- **Face Recognition Attendance**: Automatically mark attendance using real-time face detection
- **Multiple Course Support**: Manage attendance for different courses
- **Student Management**: Add, edit, and manage student profiles with photos
- **Course Management**: Create and manage multiple courses
- **Attendance Records**: View and manage attendance records with filtering options
- **Export Functionality**: Export attendance, student, and course data to CSV
- **Real-time Processing**: Process attendance in real-time with confidence scores
- **User-friendly Interface**: Modern and responsive Bootstrap-based UI
- **Email Notifications**: Automatic email notifications for attendance status
- **Environment Configuration**: Support for .env file for easy configuration

## Prerequisites

- Python 3.8 or higher
- Visual Studio C++ Build Tools
- CMake
- Webcam (for attendance capture)

## Installation

1. Clone the repository:
```bash
git clone [repository-url]
cd Smart-Attendance-System
```

2. Install Visual Studio C++ Build Tools:
- Download from [Visual Studio Downloads](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
- Install with "Desktop development with C++" workload

3. Install CMake:
- Download from [CMake Downloads](https://cmake.org/download/)
- Add CMake to system PATH

4. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

5. Install required packages:
```bash
pip install -r requirements.txt
```

## Configuration

1. Create a `.env` file in the root directory with the following variables:
```
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

2. Database setup is automatic on first run
3. Make sure the `static/uploads/students` directory exists for student photos
4. Ensure the `static/captures` directory exists for attendance captures

## Usage

1. Start the application:
```bash
python app.py
```

2. Access the web interface at `http://localhost:5000`

3. First-time setup:
   - Add courses through the Courses page
   - Register students with their photos
   - Start taking attendance

## Features in Detail

### Student Registration
- Add student details (ID, name, etc.)
- Upload student photo for face recognition
- Edit or remove student profiles

### Course Management
- Create new courses
- Assign students to courses
- View course attendance statistics

### Attendance Taking
1. Select a course
2. Start the webcam
3. System automatically:
   - Detects faces
   - Matches with registered students
   - Records attendance with timestamp
   - Marks absent students

### Records and Reports
- View attendance records with filters
- Export data in CSV format
- Review attendance details
- Edit attendance status if needed

### Email Notifications
The system supports automatic email notifications for attendance:
- Students receive instant email notifications when marked present
- Absent students receive notifications about their absence
- Emails include course details, date, and time
- Requires proper email configuration (see Configuration section)

## File Structure

```
Smart-Attendance-System/
├── app.py                 # Main application file
├── models.py             # Database models
├── face_recognition_service.py  # Face recognition logic
├── background_jobs.py    # Background processing tasks
├── email_service.py     # Email notification service
├── desktop.py          # Desktop application launcher
├── static/              # Static files (CSS, JS, uploads)
├── templates/           # HTML templates
└── instance/           # Database and instance files
```

## Troubleshooting

1. Face Recognition Issues:
   - Ensure proper lighting
   - Check if student photo is clear
   - Verify face is properly visible to camera

2. Database Issues:
   - Use `clear_attendance.py` to reset attendance records
   - Database file is in `instance/database.db`

3. Common Errors:
   - "No module named 'face_recognition'": Reinstall dependencies
   - "No camera found": Check webcam connection
   - "Build wheel failed": Install Visual C++ Build Tools
   - "Email sending failed": Check your email configuration in .env file

## Security Considerations

- Application is for development use only
- Implement proper authentication for production
- Secure the database file
- Protect student data and photos
- Keep your .env file secure and never commit it to version control

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Face Recognition library
- Flask framework
- Bootstrap for UI
- SQLAlchemy for database 
>>>>>>> b9a19c6 (initial commit)

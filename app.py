from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, flash, send_file
import cv2
import numpy as np
from datetime import datetime
import os
import atexit
from werkzeug.utils import secure_filename
from models import db, Student, Course, Attendance
import csv
from io import StringIO
DEMO_MODE = os.getenv('DEMO_MODE', '0') == '1'

# Optional imports for demo-friendly deployment (e.g., Railway). If face_recognition
# stack is unavailable, fall back to a lightweight no-op implementation.
FaceRecognitionService = None
try:
    if not DEMO_MODE:
        from face_recognition_service import FaceRecognitionService  # heavy deps (dlib)
except Exception:
    FaceRecognitionService = None

from background_jobs import BackgroundJobManager
from email_service import EmailService
import zipfile
from io import BytesIO
from flask_mail import Mail
from config import config
from database_manager import DatabaseManager, register_cli_commands
from apscheduler.schedulers.background import BackgroundScheduler

# Import CLI commands
import cli_monitor
import cli_commands

# Get the absolute path of the current directory
basedir = os.path.abspath(os.path.dirname(__file__))

# Get the environment setting
env = os.getenv('FLASK_ENV', 'development')

# Application configuration
app = Flask(__name__)
app.config.from_object(config[env])
app.secret_key = 'your-secret-key-here'  # Required for flash messages

# Email configuration (read from environment for deployments)
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', '465')),
    MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'true').lower() == 'true',
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'false').lower() == 'true',
    MAIL_USERNAME=os.getenv('MAIL_USERNAME', ''),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD', ''),
    MAIL_DEFAULT_SENDER=os.getenv('MAIL_DEFAULT_SENDER', os.getenv('MAIL_USERNAME', ''))
)

# Initialize Flask-Mail
mail = Mail(app)

# Print email configuration status
if (app.config['MAIL_USERNAME'] == 'your-email@gmail.com' or 
    app.config['MAIL_PASSWORD'] == 'your-app-password'):
    print("\nEMAIL CONFIGURATION REQUIRED:")
    print("1. Go to your Google Account settings")
    print("2. Enable 2-Step Verification if not already enabled")
    print("3. Generate an App Password:")
    print("   - Go to Security > App passwords")
    print("   - Select 'Mail' and 'Windows Computer'")
    print("   - Click 'Generate'")
    print("\nThen update these lines in app.py:")
    print("    MAIL_USERNAME='your-email@gmail.com'")
    print("    MAIL_PASSWORD='your-app-password'")
    print("    MAIL_DEFAULT_SENDER='your-email@gmail.com'\n")

# Create necessary directories
UPLOAD_FOLDER = 'static/uploads/students'
CAPTURES_FOLDER = 'static/captures'  # New folder for captured images
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CAPTURES_FOLDER, exist_ok=True)  # Create captures directory

# Database configuration
# Respect DATABASE_URL if provided via environment (e.g., Railway),
# otherwise default to local SQLite.
if not os.getenv('DATABASE_URL'):
    DB_PATH = os.path.join(basedir, 'database', 'attendance.db')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Initialize database manager
db_manager = DatabaseManager(app)

# Register CLI commands
from cli_monitor import register_cli_commands
register_cli_commands(app)

# Global variables for video capture
video_capture = None
process_frames = False
current_course_id = None
current_frame = None  # Store the current frame for capture

# Load the face detection cascade classifier
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Initialize services
face_service = None
job_manager = None
email_service = None

class DummyFaceRecognitionService:
    def __init__(self, app):
        self.app = app
        self.known_face_encodings = {}
        self.known_face_names = {}
        self.encoding_timestamp = {}
    def _add_student_encoding(self, student):
        return True
    def _match_faces(self, image_path):
        return []
    def process_pending_attendance(self):
        return None
    def verify_photo(self, photo_path):
        return {"is_valid": True, "message": "Demo mode: photo accepted", "face_count": 1}

def initialize_services():
    global face_service, job_manager, email_service
    if face_service is None:
        if FaceRecognitionService is not None:
            face_service = FaceRecognitionService(app)
        else:
            face_service = DummyFaceRecognitionService(app)
        # Load face encodings for existing students
        with app.app_context():
            students = Student.query.all()
            for student in students:
                if student.photo_path:
                    face_service._add_student_encoding(student)
    
    if job_manager is None:
        job_manager = BackgroundJobManager(app, face_service)
        job_manager.start()
        
    if email_service is None:
        email_service = EmailService(app)

# Replace before_first_request with new pattern
with app.app_context():
    initialize_services()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}

@app.route('/')
def dashboard():
    total_students = Student.query.count()
    total_courses = Course.query.count()
    today = datetime.now().date()
    present_today = Attendance.query.filter_by(date=today, status='present').count()
    
    if total_students > 0:
        attendance_rate = (present_today / total_students) * 100
    else:
        attendance_rate = 0
        
    return render_template('dashboard.html',
                         total_students=total_students,
                         total_courses=total_courses,
                         present_today=present_today,
                         attendance_rate=f"{attendance_rate:.1f}%")

@app.route('/take-attendance')
def take_attendance():
    courses = Course.query.all()
    return render_template('take_attendance.html', courses=courses)

@app.route('/register-student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        # Get form data
        name = request.form.get('name')
        student_id = request.form.get('student_id')
        email = request.form.get('email')
        course_ids = request.form.get('courses').split(',') if request.form.get('courses') else []  # Split the comma-separated string
        
        # Check if student ID already exists
        if Student.query.filter_by(student_id=student_id).first():
            flash('Student ID already exists!', 'error')
            return redirect(url_for('register_student'))
        
        # Handle photo upload
        if 'photo' not in request.files:
            flash('No photo uploaded!', 'error')
            return redirect(url_for('register_student'))
            
        photo = request.files['photo']
        if photo.filename == '':
            flash('No photo selected!', 'error')
            return redirect(url_for('register_student'))
            
        if photo and allowed_file(photo.filename):
            try:
                # Secure the filename and create paths
                filename = secure_filename(f"{student_id}_{photo.filename}")
                photo_path = f"uploads/students/{filename}"
                full_path = os.path.join(basedir, 'static', 'uploads', 'students', filename)
                
                # Ensure the upload directory exists
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                # Save the file
                photo.save(full_path)
                
                # Verify the photo using face recognition service
                verification_result = face_service.verify_photo(full_path)
                
                if not verification_result['is_valid']:
                    os.remove(full_path)
                    flash(verification_result['message'], 'error')
                    return redirect(url_for('register_student'))
                
                # Create new student
                student = Student(
                    name=name,
                    student_id=student_id,
                    email=email,
                    photo_path=photo_path
                )
                
                # Add selected courses
                for course_id in course_ids:
                    if course_id:  # Skip empty strings
                        course = Course.query.get(int(course_id))
                        if course:
                            student.courses.append(course)
                
                db.session.add(student)
                db.session.commit()
                
                # Add face encoding for the new student
                if face_service._add_student_encoding(student):
                    flash('Student registered successfully!', 'success')
                else:
                    db.session.delete(student)
                    db.session.commit()
                    os.remove(full_path)
                    flash('Error processing student photo. Please try with a different photo.', 'error')
                    return redirect(url_for('register_student'))
                
                return redirect(url_for('dashboard'))
                
            except Exception as e:
                db.session.rollback()
                # Clean up the uploaded file if it exists
                if os.path.exists(full_path):
                    os.remove(full_path)
                flash(f'Error registering student: {str(e)}', 'error')
                return redirect(url_for('register_student'))
        else:
            flash('Invalid file type! Please upload a PNG or JPEG image.', 'error')
            return redirect(url_for('register_student'))
    
    # GET request - show the registration form
    courses = Course.query.all()
    return render_template('register_student.html', courses=courses)

@app.route('/start_capture', methods=['POST'])
def start_capture():
    global video_capture, process_frames, current_course_id
    
    data = request.get_json()
    current_course_id = int(data.get('course_id'))  # Convert to integer
    print(f"Debug - Setting current_course_id to: {current_course_id}")
    print(f"Debug - Course name: {Course.query.get(current_course_id).name}")
    
    if video_capture is None:
        video_capture = cv2.VideoCapture(0)
    
    process_frames = True
    return jsonify({"status": "success"})

@app.route('/capture_attendance', methods=['POST'])
def capture_attendance():
    global current_frame, current_course_id
    
    if current_frame is None:
        return jsonify({
            "status": "error",
            "message": "No frame available to capture"
        })
    
    try:
        # Create a directory for today's captures
        today = datetime.now().strftime('%Y-%m-%d')
        course = Course.query.get(current_course_id)
        if not course:
            return jsonify({
                "status": "error",
                "message": "Invalid course"
            })
            
        capture_dir = os.path.join(CAPTURES_FOLDER, today)
        os.makedirs(capture_dir, exist_ok=True)
        
        # Save the current frame
        timestamp = datetime.now().strftime('%H-%M-%S')
        filename = f"capture_{course.identifier}_{timestamp}.jpg"
        filepath = os.path.join(capture_dir, filename)
        relative_path = os.path.join('captures', today, filename)
        
        # Save the frame
        cv2.imwrite(filepath, current_frame)
        
        # Get current date and time
        current_date = datetime.now().date()
        current_time = datetime.now().time()
        
        # Get all students in the course
        course_students = course.students
        
        # Process the capture immediately
        matches = face_service._match_faces(filepath)
        
        if matches:
            recognized_students = []
            already_marked_students = []
            not_in_course_students = []
            
            for student_id, confidence in matches:
                student = Student.query.filter_by(student_id=student_id).first()
                
                if not student:
                    continue
                
                # Check if student is enrolled in this course
                if current_course_id not in [c.id for c in student.courses]:
                    not_in_course_students.append(student.name)
                    continue
                
                # Check if attendance already marked for this student today
                existing_attendance = Attendance.query.filter_by(
                    student_id=student.id,
                    course_id=current_course_id,
                    date=current_date
                ).first()
                
                if existing_attendance:
                    already_marked_students.append(student.name)
                    continue
                
                # Create attendance record for the recognized student
                attendance = Attendance(
                    student_id=student.id,
                    course_id=current_course_id,
                    date=current_date,
                    time=current_time,
                    status='present',
                    capture_path=relative_path.replace('\\', '/'),
                    confidence=confidence
                )
                
                db.session.add(attendance)
                recognized_students.append(student)
                
                # Send email notification for present student
                if student.email:
                    email_service.send_attendance_notification(
                        student_email=student.email,
                        student_name=student.name,
                        course_name=course.name,
                        status='present',
                        date=current_date.strftime('%B %d, %Y'),
                        time=current_time.strftime('%I:%M %p')
                    )
            
            # Prepare response message
            messages = []
            if recognized_students:
                recognized_names = [student.name for student in recognized_students]
                messages.append(f"Attendance marked for: {', '.join(recognized_names)}")
            
            if already_marked_students:
                messages.append(f"Already marked present today: {', '.join(already_marked_students)}")
            
            if not_in_course_students:
                messages.append(f"Not registered in this course: {', '.join(not_in_course_students)}")
            
            if not recognized_students and not already_marked_students and not not_in_course_students:
                # No valid students were recognized
                attendance = Attendance(
                    course_id=current_course_id,
                    date=current_date,
                    time=current_time,
                    status='unknown',
                    capture_path=relative_path.replace('\\', '/'),
                    confidence=0.0
                )
                db.session.add(attendance)
                db.session.commit()
                
                return jsonify({
                    "status": "warning",
                    "message": "No matching students found in the capture"
                })
            
            # Mark other students as absent if they don't have attendance yet
            absent_notifications = []
            for course_student in course_students:
                if course_student not in recognized_students:
                    # Check if this student already has attendance for today
                    existing = Attendance.query.filter_by(
                        student_id=course_student.id,
                        course_id=current_course_id,
                        date=current_date
                    ).first()
                    
                    if not existing:
                        # Create absent record
                        absent_record = Attendance(
                            student_id=course_student.id,
                            course_id=current_course_id,
                            date=current_date,
                            time=current_time,
                            status='absent',
                            confidence=0.0
                        )
                        db.session.add(absent_record)
                        
                        # Add to absent notifications if student has email
                        if course_student.email:
                            absent_notifications.append({
                                'email': course_student.email,
                                'name': course_student.name,
                                'course': course.name,
                                'status': 'absent',
                                'date': current_date.strftime('%B %d, %Y'),
                                'time': current_time.strftime('%I:%M %p')
                            })
            
            db.session.commit()
            
            # Send absent notifications in bulk
            if absent_notifications:
                email_service.send_bulk_attendance_notifications(absent_notifications)
            
            return jsonify({
                "status": "info" if already_marked_students else "success",
                "message": "\n".join(messages),
                "confidence": f"{min([conf for _, conf in matches]) * 100:.1f}% - {max([conf for _, conf in matches]) * 100:.1f}%"
            })
        else:
            # Create a pending record for manual review
            attendance = Attendance(
                course_id=current_course_id,
                date=current_date,
                time=current_time,
                status='unknown',
                capture_path=relative_path.replace('\\', '/'),
                confidence=0.0
            )
            
            db.session.add(attendance)
            db.session.commit()
            
            return jsonify({
                "status": "warning",
                "message": "No matching students found. The capture has been saved for review."
            })
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Error capturing attendance: {str(e)}"
        })

@app.route('/stop_capture', methods=['POST'])
def stop_capture():
    global video_capture, process_frames, current_course_id, current_frame
    
    process_frames = False
    current_course_id = None
    current_frame = None
    
    if video_capture is not None:
        video_capture.release()
        video_capture = None
    
    return jsonify({"status": "success"})

def generate_frames():
    global video_capture, process_frames, current_frame
    
    while True:
        if not process_frames:
            continue
            
        success, frame = video_capture.read()
        if not success:
            break
        
        # Store the current frame for capture
        current_frame = frame.copy()
        
        # Convert to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )
        
        # Draw rectangles around faces
        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
        
        # Convert frame to jpg
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/records')
def records():
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    course_id = request.args.get('course')
    status = request.args.get('status')

    # Base query with eager loading of relationships using left joins
    query = Attendance.query.outerjoin(Student).outerjoin(Course)

    # Apply filters
    if start_date:
        query = query.filter(Attendance.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Attendance.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if course_id:
        query = query.filter(Attendance.course_id == int(course_id))
    if status:
        query = query.filter(Attendance.status == status)

    # Get records with related data
    records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()

    # Calculate statistics
    stats = {
        'total': len(records),
        'present': len([r for r in records if r.status == 'present']),
        'absent': len([r for r in records if r.status == 'absent']),
        'late': len([r for r in records if r.status == 'late']),
        'unknown': len([r for r in records if r.status == 'unknown']),
        'pending': len([r for r in records if r.status == 'pending'])
    }

    # Get all courses for filter dropdown
    courses = Course.query.all()

    return render_template('records.html', 
                         records=records, 
                         stats=stats, 
                         courses=courses,
                         current_filters={
                             'start_date': start_date,
                             'end_date': end_date,
                             'course_id': course_id,
                             'status': status
                         })

@app.route('/students')
def students_list():
    students = Student.query.all()
    return render_template('students.html', students=students)

@app.route('/students/<int:student_id>/view')
def view_student(student_id):
    student = Student.query.get_or_404(student_id)
    return render_template('view_student.html', student=student)

@app.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        try:
            # Get the new student_id from the form
            new_student_id = request.form.get('student_id')
            
            # Check if the new student_id already exists (excluding current student)
            if new_student_id != student.student_id and Student.query.filter_by(student_id=new_student_id).first():
                flash('Student ID already exists!', 'error')
                return redirect(url_for('edit_student', student_id=student_id))
            
            # Update student information
            student.student_id = new_student_id
            student.name = request.form.get('name')
            student.email = request.form.get('email')
            
            # Update courses
            course_ids = request.form.get('courses').split(',') if request.form.get('courses') else []
            student.courses = []  # Clear existing courses
            for course_id in course_ids:
                if course_id:  # Skip empty strings
                    course = Course.query.get(int(course_id))
                    if course:
                        student.courses.append(course)
            
            # Handle photo update if provided
            if 'photo' in request.files and request.files['photo'].filename != '':
                photo = request.files['photo']
                
                if allowed_file(photo.filename):
                    # Create new filename and paths
                    filename = secure_filename(f"{student.student_id}_{photo.filename}")
                    photo_path = f"uploads/students/{filename}"
                    full_path = os.path.join(basedir, 'static', 'uploads', 'students', filename)
                    
                    # Verify the new photo
                    photo.save(full_path)
                    verification_result = face_service.verify_photo(full_path)
                    
                    if not verification_result['is_valid']:
                        os.remove(full_path)
                        flash(verification_result['message'], 'error')
                        return redirect(url_for('edit_student', student_id=student_id))
                    
                    # Remove old photo if it exists
                    if student.photo_path:
                        old_photo_path = os.path.join(basedir, 'static', student.photo_path)
                        if os.path.exists(old_photo_path):
                            os.remove(old_photo_path)
                    
                    # Update student photo path
                    student.photo_path = photo_path
                    
                    # Update face encoding
                    if not face_service._add_student_encoding(student):
                        os.remove(full_path)
                        flash('Error processing student photo. Please try with a different photo.', 'error')
                        return redirect(url_for('edit_student', student_id=student_id))
                else:
                    flash('Invalid file type! Please upload a PNG or JPEG image.', 'error')
                    return redirect(url_for('edit_student', student_id=student_id))
            
            db.session.commit()
            flash('Student updated successfully!', 'success')
            return redirect(url_for('students_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating student: {str(e)}', 'error')
            return redirect(url_for('edit_student', student_id=student_id))
    
    courses = Course.query.all()
    return render_template('edit_student.html', student=student, courses=courses)

@app.route('/students/<int:student_id>/delete', methods=['POST'])
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    try:
        # Delete student photo if it exists
        if student.photo_path:
            photo_path = os.path.join(basedir, 'static', student.photo_path)
            if os.path.exists(photo_path):
                os.remove(photo_path)
        
        # Remove face encoding from the service
        if student.student_id in face_service.known_face_encodings:
            del face_service.known_face_encodings[student.student_id]
            del face_service.known_face_names[student.student_id]
            del face_service.encoding_timestamp[student.student_id]
        
        # Delete attendance records
        Attendance.query.filter_by(student_id=student.id).delete()
        
        # Remove student from all courses (the association table entries will be automatically deleted)
        student.courses = []
        
        # Delete student record
        db.session.delete(student)
        db.session.commit()
        
        flash('Student deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'error')
    
    return redirect(url_for('students_list'))

@app.route('/courses')
def courses():
    courses = Course.query.all()
    
    # Calculate statistics
    total_courses = len(courses)
    total_students = Student.query.count()
    
    # Calculate average attendance rate
    attendance_records = Attendance.query.all()
    if attendance_records:
        present_count = len([a for a in attendance_records if a.status == 'present'])
        total_count = len(attendance_records)
        avg_attendance = (present_count / total_count) * 100
    else:
        avg_attendance = 0
    
    stats = {
        'total_courses': total_courses,
        'total_students': total_students,
        'avg_attendance': f"{avg_attendance:.1f}"
    }
    
    return render_template('courses.html', courses=courses, stats=stats)

@app.route('/courses/add', methods=['POST'])
def add_course():
    name = request.form.get('name')
    course_id = request.form.get('course_id')
    
    if not name or not course_id:
        flash('Course name and ID are required!', 'error')
        return redirect(url_for('courses'))
    
    # Check if course already exists
    if Course.query.filter_by(name=name).first():
        flash('A course with this name already exists!', 'error')
        return redirect(url_for('courses'))
        
    if Course.query.filter_by(identifier=course_id).first():
        flash('A course with this ID already exists!', 'error')
        return redirect(url_for('courses'))
    
    course = Course(name=name, identifier=course_id)
    try:
        db.session.add(course)
        db.session.commit()
        flash('Course added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error adding course. Please try again.', 'error')
    
    return redirect(url_for('courses'))

@app.route('/courses/<int:course_id>/view')
def view_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    # Calculate course statistics
    course_attendances = Attendance.query.filter_by(course_id=course_id).all()
    total_records = len(course_attendances)
    
    if total_records > 0:
        present_count = len([a for a in course_attendances if a.status == 'present'])
        absent_count = len([a for a in course_attendances if a.status == 'absent'])
        late_count = len([a for a in course_attendances if a.status == 'late'])
        
        stats = {
            'present_rate': round((present_count / total_records) * 100, 1),
            'absent_rate': round((absent_count / total_records) * 100, 1),
            'late_rate': round((late_count / total_records) * 100, 1)
        }
    else:
        stats = {
            'present_rate': 0,
            'absent_rate': 0,
            'late_rate': 0
        }
    
    # Calculate student-specific statistics
    student_stats = {}
    for student in course.students:
        student_attendances = [a for a in course_attendances if a.student_id == student.id]
        total_student_records = len(student_attendances)
        
        if total_student_records > 0:
            present_student_count = len([a for a in student_attendances if a.status == 'present'])
            attendance_rate = (present_student_count / total_student_records) * 100
        else:
            attendance_rate = 0
            
        student_stats[student.id] = {
            'attendance_rate': round(attendance_rate, 1)
        }
    
    return render_template('view_course.html', 
                         course=course, 
                         stats=stats, 
                         student_stats=student_stats)

@app.route('/courses/<int:course_id>/edit', methods=['POST'])
def edit_course(course_id):
    course = Course.query.get_or_404(course_id)
    name = request.form.get('name')
    new_course_id = request.form.get('course_id')
    
    if not name or not new_course_id:
        flash('Course name and ID are required!', 'error')
        return redirect(url_for('view_course', course_id=course_id))
    
    # Check if another course with this name exists
    existing_course = Course.query.filter_by(name=name).first()
    if existing_course and existing_course.id != course_id:
        flash('A course with this name already exists!', 'error')
        return redirect(url_for('view_course', course_id=course_id))
        
    # Check if another course with this ID exists
    existing_course = Course.query.filter_by(identifier=new_course_id).first()
    if existing_course and existing_course.id != course_id:
        flash('A course with this ID already exists!', 'error')
        return redirect(url_for('view_course', course_id=course_id))
    
    try:
        course.name = name
        course.identifier = new_course_id
        db.session.commit()
        flash('Course updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error updating course. Please try again.', 'error')
    
    return redirect(url_for('view_course', course_id=course_id))

@app.route('/courses/<int:course_id>/delete', methods=['POST'])
def delete_course(course_id):
    course = Course.query.get_or_404(course_id)
    
    try:
        # Delete associated attendance records
        Attendance.query.filter_by(course_id=course_id).delete()
        
        # Remove all students from this course (clear the many-to-many relationship)
        course.students = []
        
        # Delete the course
        db.session.delete(course)
        db.session.commit()
        flash('Course deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting course. Please try again.', 'error')
    
    return redirect(url_for('courses'))

@app.route('/export/students')
def export_students():
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['Student ID', 'Name', 'Email', 'Courses', 'Registration Date'])
    
    # Write data
    students = Student.query.all()
    for student in students:
        # Get all courses for this student
        courses_str = '; '.join([f"{course.identifier} - {course.name}" for course in student.courses])
        
        writer.writerow([
            student.student_id,
            student.name,
            student.email or '',
            courses_str or 'No courses',
            student.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    # Convert to bytes
    output.seek(0)
    bytes_output = BytesIO()
    bytes_output.write(output.getvalue().encode('utf-8'))
    bytes_output.seek(0)
    
    return send_file(
        bytes_output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'students_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route('/export/courses')
def export_courses():
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['Course ID', 'Course Name', 'Total Students', 'Creation Date'])
    
    # Write data
    courses = Course.query.all()
    for course in courses:
        writer.writerow([
            course.identifier,
            course.name,
            len(course.students),
            course.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    # Convert to bytes
    output.seek(0)
    bytes_output = BytesIO()
    bytes_output.write(output.getvalue().encode('utf-8'))
    bytes_output.seek(0)
    
    return send_file(
        bytes_output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'courses_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route('/export/attendance')
def export_attendance():
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['Date', 'Time', 'Student ID', 'Student Name', 'Course ID', 'Course Name', 'Status', 'Confidence'])
    
    # Write data
    attendances = Attendance.query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
    for attendance in attendances:
        writer.writerow([
            attendance.date.strftime('%Y-%m-%d'),
            attendance.time.strftime('%H:%M:%S'),
            attendance.student.student_id if attendance.student else 'N/A',
            attendance.student.name if attendance.student else 'Unknown',
            attendance.course.identifier if attendance.course else 'N/A',
            attendance.course.name if attendance.course else 'N/A',
            attendance.status,
            f"{attendance.confidence:.2f}" if attendance.confidence else ''
        ])
    
    # Convert to bytes
    output.seek(0)
    bytes_output = BytesIO()
    bytes_output.write(output.getvalue().encode('utf-8'))
    bytes_output.seek(0)
    
    return send_file(
        bytes_output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route('/export/all')
def export_all():
    # Create a zip file in memory
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w') as zf:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export students
        students_output = StringIO()
        students_writer = csv.writer(students_output)
        students_writer.writerow(['Student ID', 'Name', 'Email', 'Courses', 'Registration Date'])
        students = Student.query.all()
        for student in students:
            # Get all courses for this student
            courses_str = '; '.join([f"{course.identifier} - {course.name}" for course in student.courses])
            
            students_writer.writerow([
                student.student_id,
                student.name,
                student.email or '',
                courses_str or 'No courses',
                student.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        zf.writestr(f'students_{timestamp}.csv', students_output.getvalue())
        
        # Export courses
        courses_output = StringIO()
        courses_writer = csv.writer(courses_output)
        courses_writer.writerow(['Course ID', 'Course Name', 'Total Students', 'Creation Date'])
        courses = Course.query.all()
        for course in courses:
            courses_writer.writerow([
                course.identifier,
                course.name,
                len(course.students),
                course.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
        zf.writestr(f'courses_{timestamp}.csv', courses_output.getvalue())
        
        # Export attendance
        attendance_output = StringIO()
        attendance_writer = csv.writer(attendance_output)
        attendance_writer.writerow(['Date', 'Time', 'Student ID', 'Student Name', 'Course ID', 'Course Name', 'Status', 'Confidence'])
        attendances = Attendance.query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        for attendance in attendances:
            attendance_writer.writerow([
                attendance.date.strftime('%Y-%m-%d'),
                attendance.time.strftime('%H:%M:%S'),
                attendance.student.student_id if attendance.student else 'N/A',
                attendance.student.name if attendance.student else 'Unknown',
                attendance.course.identifier if attendance.course else 'N/A',
                attendance.course.name if attendance.course else 'N/A',
                attendance.status,
                f"{attendance.confidence:.2f}" if attendance.confidence else ''
            ])
        zf.writestr(f'attendance_{timestamp}.csv', attendance_output.getvalue())
    
    # Prepare the zip file for sending
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'all_data_{timestamp}.zip'
    )

# Add new route for processing pending attendance
@app.route('/process-pending', methods=['POST'])
def process_pending_attendance():
    try:
        face_service.process_pending_attendance()
        return jsonify({
            "status": "success",
            "message": "Processed pending attendance records"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

# Initialize database tables and default data
def init_db():
    with app.app_context():
        print('Starting database initialization...')
        
        # Check if tables exist
        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        # If the student_courses table doesn't exist, we need to migrate
        need_migration = 'student_courses' not in existing_tables and 'student' in existing_tables
        
        if need_migration:
            print('Migrating database to new schema...')
            # Backup existing student data
            students_data = []
            try:
                students = Student.query.all()
                for student in students:
                    students_data.append({
                        'student_id': student.student_id,
                        'name': student.name,
                        'email': student.email,
                        'photo_path': student.photo_path,
                        'course_id': student.course_id,
                        'created_at': student.created_at
                    })
            except Exception as e:
                print(f'Error backing up student data: {str(e)}')
                students_data = []
            
            # Drop all tables
            db.drop_all()
            print('Dropped existing tables.')
        
        # Create all tables
        db.create_all()
        print('Created new tables with updated schema.')
        
        # Restore data if we migrated
        if need_migration and students_data:
            print('Restoring student data...')
            try:
                for data in students_data:
                    student = Student(
                        student_id=data['student_id'],
                        name=data['name'],
                        email=data['email'],
                        photo_path=data['photo_path'],
                        created_at=data['created_at']
                    )
                    # Add the student to their original course
                    course = Course.query.get(data['course_id'])
                    if course:
                        student.courses.append(course)
                    db.session.add(student)
                db.session.commit()
                print('Student data restored successfully.')
            except Exception as e:
                db.session.rollback()
                print(f'Error restoring student data: {str(e)}')
        
        # Add default courses if no courses exist
        if Course.query.count() == 0:
            print('Adding default courses...')
            default_courses = [
                Course(identifier="CS101", name="Computer Science 101"),
                Course(identifier="MATH202", name="Mathematics 202"),
                Course(identifier="PHYS301", name="Physics 301")
            ]
            db.session.add_all(default_courses)
            try:
                db.session.commit()
                print('Default courses added successfully.')
            except Exception as e:
                db.session.rollback()
                print('Error adding default courses:', str(e))
        else:
            print(f'Found existing tables: {existing_tables}')
            print('Database already initialized.')

@app.cli.command("init-db")
def init_db_command():
    """Initialize the database tables and add default data."""
    init_db()
    print('Database initialization completed.')

# Initialize database on startup (only if tables don't exist)
init_db()

@app.route('/attendance/review')
def attendance_review():
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    course_id = request.args.get('course')
    status = request.args.get('status')

    # Base query
    query = Attendance.query

    # Apply filters
    if start_date:
        query = query.filter(Attendance.date >= datetime.strptime(start_date, '%Y-%m-%d').date())
    if end_date:
        query = query.filter(Attendance.date <= datetime.strptime(end_date, '%Y-%m-%d').date())
    if course_id:
        query = query.filter(Attendance.course_id == int(course_id))
    if status:
        query = query.filter(Attendance.status == status)

    # Get records with related data
    records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()

    # Add status colors for badges
    for record in records:
        if record.status == 'present':
            record.status_color = 'success'
        elif record.status == 'absent':
            record.status_color = 'danger'
        elif record.status == 'pending':
            record.status_color = 'warning'
        else:
            record.status_color = 'secondary'

    # Calculate statistics
    stats = {
        'total': len(records),
        'present': len([r for r in records if r.status == 'present']),
        'pending': len([r for r in records if r.status == 'pending']),
        'unknown': len([r for r in records if r.status == 'unknown'])
    }

    # Get all courses and students for filters and editing
    courses = Course.query.all()
    students = Student.query.all()

    return render_template('attendance_review.html',
                         records=records,
                         stats=stats,
                         courses=courses,
                         students=students)

@app.route('/attendance/<int:record_id>/update', methods=['POST'])
def update_attendance(record_id):
    record = Attendance.query.get_or_404(record_id)
    
    # Get form data
    student_id = request.form.get('student_id')
    status = request.form.get('status')
    
    try:
        if student_id:
            record.student_id = int(student_id)
        else:
            record.student_id = None
            
        record.status = status
        
        # If manually setting a student, set confidence to 1.0
        if student_id and status == 'present':
            record.confidence = 1.0
        elif not student_id:
            record.confidence = 0.0
        
        db.session.commit()
        flash('Attendance record updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating attendance record: {str(e)}', 'error')
    
    return redirect(url_for('attendance_review',
                          start_date=request.args.get('start_date'),
                          end_date=request.args.get('end_date'),
                          course=request.args.get('course'),
                          status=request.args.get('status')))

# Register cleanup function
@atexit.register
def cleanup():
    global video_capture, job_manager
    if video_capture:
        video_capture.release()
    if job_manager:
        job_manager.stop()

@app.route('/clear_records', methods=['POST'])
def clear_records():
    if request.method == 'POST':
        confirmation = request.form.get('confirmation')
        if confirmation != 'DELETE':
            flash('Please type DELETE to confirm record deletion.', 'error')
            return redirect(url_for('records'))

        clear_option = request.form.get('clear_option')
        
        try:
            if clear_option == 'all':
                # Delete all records
                db.session.query(Attendance).delete()
                message = 'All attendance records have been cleared.'
            
            elif clear_option == 'date_range':
                start_date = request.form.get('start_date')
                end_date = request.form.get('end_date')
                
                if not start_date or not end_date:
                    flash('Please provide both start and end dates.', 'error')
                    return redirect(url_for('records'))
                
                # Convert string dates to datetime objects
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                # Delete records within date range
                db.session.query(Attendance).filter(
                    Attendance.date >= start_date,
                    Attendance.date <= end_date
                ).delete()
                
                message = f'Attendance records from {start_date} to {end_date} have been cleared.'
            
            elif clear_option == 'course':
                course_id = request.form.get('course_id')
                if not course_id:
                    flash('Please select a course.', 'error')
                    return redirect(url_for('records'))
                
                # Get course name for the message
                course = Course.query.get(course_id)
                if not course:
                    flash('Invalid course selected.', 'error')
                    return redirect(url_for('records'))
                
                # Delete records for specific course
                db.session.query(Attendance).filter_by(course_id=course_id).delete()
                message = f'Attendance records for {course.name} have been cleared.'
            
            db.session.commit()
            flash(message, 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error clearing records: {str(e)}', 'error')
        
        return redirect(url_for('records'))

# Scheduled tasks for database maintenance
scheduler = BackgroundScheduler()

@scheduler.scheduled_job('cron', hour=0)  # Run at midnight
def scheduled_backup():
    with app.app_context():
        db_manager.create_backup()

@scheduler.scheduled_job('cron', day_of_week='sun')  # Run weekly on Sunday
def scheduled_optimization():
    with app.app_context():
        db_manager.optimize_database()

scheduler.start()

# Register cleanup on app shutdown
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(debug=True) 
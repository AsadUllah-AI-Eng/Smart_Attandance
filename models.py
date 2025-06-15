from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Association table for student-course relationship
student_courses = db.Table('student_courses',
    db.Column('student_id', db.Integer, db.ForeignKey('student.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    identifier = db.Column(db.String(20), unique=True, nullable=False)  # Course ID like CS101
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    students = db.relationship('Student', 
                             secondary=student_courses,
                             backref=db.backref('courses', lazy=True),
                             lazy=True)
    attendances = db.relationship('Attendance', backref='course', lazy=True)

    def __repr__(self):
        return f'<Course {self.identifier}: {self.name}>'

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name
        }

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    photo_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'name': self.name,
            'email': self.email,
            'photo_path': self.photo_path,
            'courses': [course.name for course in self.courses]
        }

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # present, absent, late, pending, unknown
    confidence = db.Column(db.Float, nullable=True)
    capture_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationships
    student = db.relationship('Student', backref=db.backref('attendances', lazy=True))
    
    def __repr__(self):
        return f'<Attendance {self.date} {self.time} {self.status}>' 
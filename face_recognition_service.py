import face_recognition
import cv2
import numpy as np
import os
from datetime import datetime
from models import db, Student, Attendance
from typing import List, Tuple, Optional, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FaceRecognitionService:
    def __init__(self, app):
        self.app = app
        self.known_face_encodings = {}  # student_id: encoding
        self.known_face_names = {}      # student_id: name
        self.encoding_timestamp = {}    # student_id: last_update_time
        self.min_confidence_threshold = 0.6
        self.load_known_faces()
    
    def load_known_faces(self):
        """Load face encodings for all registered students"""
        with self.app.app_context():
            students = Student.query.all()
            for student in students:
                self._add_student_encoding(student)
    
    def _add_student_encoding(self, student: Student) -> bool:
        """Generate and store face encoding for a single student"""
        try:
            # Get full path to student photo
            photo_path = os.path.join(self.app.static_folder, student.photo_path)
            
            # Load and encode face
            image = face_recognition.load_image_file(photo_path)
            
            # First detect face locations
            face_locations = face_recognition.face_locations(image, model="hog")
            
            if not face_locations:
                logger.warning(f"No face found in photo for student {student.name}")
                return False
            
            if len(face_locations) > 1:
                logger.warning(f"Multiple faces found in photo for student {student.name}. Using the largest face.")
                # Get the largest face by area
                face_locations = [max(face_locations, key=lambda rect: (rect[2] - rect[0]) * (rect[1] - rect[3]))]
            
            # Get encodings for the detected face
            encodings = face_recognition.face_encodings(image, face_locations)
            
            if not encodings:
                logger.warning(f"Could not generate encoding for student {student.name}")
                return False
            
            # Store encoding and metadata
            self.known_face_encodings[student.student_id] = encodings[0]
            self.known_face_names[student.student_id] = student.name
            self.encoding_timestamp[student.student_id] = datetime.now()
            
            logger.info(f"Successfully added face encoding for student {student.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding face encoding for student {student.name}: {str(e)}")
            return False
    
    def process_pending_attendance(self):
        """Process all pending attendance records"""
        with self.app.app_context():
            pending_records = Attendance.query.filter_by(status='pending').all()
            
            for record in pending_records:
                if not record.capture_path:
                    continue
                
                # Get full path to captured image
                capture_path = os.path.join(self.app.static_folder, record.capture_path)
                
                # Process the capture and get all matches
                matches = self._match_faces(capture_path)
                
                if matches:
                    # Take the match with highest confidence
                    student_id, confidence = max(matches, key=lambda x: x[1])
                    # Update attendance record
                    record.student_id = student_id
                    record.status = 'present'
                    record.confidence = confidence
                else:
                    # Mark as unknown if no match found
                    record.status = 'unknown'
                    record.confidence = 0.0
                
                db.session.commit()
    
    def _match_faces(self, image_path: str) -> List[Tuple[int, float]]:
        """Match all faces in captured image against known faces"""
        try:
            # Load the captured image
            image = face_recognition.load_image_file(image_path)
            
            # Detect faces in the image
            face_locations = face_recognition.face_locations(image, model="hog")
            if not face_locations:
                return []
            
            # Get encodings for all detected faces
            face_encodings = face_recognition.face_encodings(image, face_locations)
            
            matches = []
            for face_encoding in face_encodings:
                # Compare with all known faces
                face_matches = []
                
                for student_id, known_encoding in self.known_face_encodings.items():
                    # Calculate face distance
                    face_distances = face_recognition.face_distance([known_encoding], face_encoding)
                    
                    if len(face_distances) == 0:
                        continue
                    
                    # Convert distance to confidence (0-1 range)
                    confidence = 1 - face_distances[0]
                    
                    # Add to matches if above threshold
                    if confidence > self.min_confidence_threshold:
                        face_matches.append((student_id, confidence))
                
                # Sort matches by confidence and get the best match for this face
                if face_matches:
                    best_match = max(face_matches, key=lambda x: x[1])
                    matches.append(best_match)
            
            return matches
            
        except Exception as e:
            logger.error(f"Error matching faces: {str(e)}")
            return []
    
    def update_student_encoding(self, student_id: str) -> bool:
        """Update face encoding for a specific student"""
        with self.app.app_context():
            student = Student.query.filter_by(student_id=student_id).first()
            if student:
                return self._add_student_encoding(student)
            return False
    
    def verify_photo(self, photo_path: str) -> Dict:
        """Verify if a photo is suitable for face recognition"""
        try:
            image = face_recognition.load_image_file(photo_path)
            face_locations = face_recognition.face_locations(image, model="hog")
            
            result = {
                "is_valid": False,
                "message": "",
                "face_count": len(face_locations)
            }
            
            if len(face_locations) == 0:
                result["message"] = "No face detected in the photo"
            elif len(face_locations) > 1:
                result["message"] = "Multiple faces detected in the photo"
            else:
                # Check if face is large enough
                top, right, bottom, left = face_locations[0]
                face_height = bottom - top
                face_width = right - left
                image_height, image_width = image.shape[:2]
                
                min_face_size_ratio = 0.2  # Face should be at least 20% of image height
                if face_height < image_height * min_face_size_ratio:
                    result["message"] = "Face is too small in the photo"
                else:
                    result["is_valid"] = True
                    result["message"] = "Photo is suitable for face recognition"
            
            return result
            
        except Exception as e:
            logger.error(f"Error verifying photo: {str(e)}")
            return {
                "is_valid": False,
                "message": f"Error processing photo: {str(e)}",
                "face_count": 0
            } 
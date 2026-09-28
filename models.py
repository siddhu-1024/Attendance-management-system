from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# =============================================================================
# USER / FACULTY / ADMIN MODEL
# =============================================================================

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    department = db.Column(db.String(50), nullable=False, default="CAI")
    role = db.Column(db.String(20), nullable=False, default="faculty")  # 'admin' or 'faculty'
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        # Support both hashed passwords and the legacy plaintext fallback
        if self.password_hash.startswith(('scrypt:', 'pbkdf2:')):
            return check_password_hash(self.password_hash, password)
        return self.password_hash == password


# =============================================================================
# SUBJECT & SECTION MODELS
# =============================================================================

class Subject(db.Model):
    __tablename__ = 'subjects'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(50), nullable=False, default="CAI")
    semester = db.Column(db.String(20), default="Semester 1")


class Section(db.Model):
    __tablename__ = 'sections'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    department = db.Column(db.String(50), nullable=False, default="CAI")
    year = db.Column(db.String(20), default="2nd Year")


# =============================================================================
# STUDENT MODEL
# =============================================================================

class Student(db.Model):
    __tablename__ = 'student'

    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(50), nullable=False, default="CAI")
    section = db.Column(db.String(50), nullable=False, default="CAI-A")
    email = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    records = db.relationship('AttendanceRecord', backref='student_rel', lazy='dynamic', cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not password:
            return False
        # Student password is their roll number (case-insensitive support)
        if str(password).strip().upper() == str(self.roll_no).strip().upper():
            return True
        if not self.password_hash:
            return str(password).strip() in ["student123", self.roll_no, self.roll_no.lower(), self.roll_no.upper()]
        if self.password_hash.startswith(('scrypt:', 'pbkdf2:')):
            return check_password_hash(self.password_hash, password)
        return self.password_hash == password or str(password).strip().upper() == str(self.roll_no).strip().upper() or password == "student123"



# =============================================================================
# ATTENDANCE SESSION MODEL
# =============================================================================

class AttendanceSession(db.Model):
    __tablename__ = 'attendance_sessions'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False, index=True)  # YYYY-MM-DD
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True)
    subject_name = db.Column(db.String(100), nullable=False, default="Data Structures")
    section = db.Column(db.String(50), nullable=False, default="CAI-A")
    period = db.Column(db.String(20), nullable=False, default="1")
    topic = db.Column(db.String(200), nullable=True)
    faculty_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    faculty_name = db.Column(db.String(120), nullable=False, default="Faculty")
    
    total_students = db.Column(db.Integer, default=0)
    present_count = db.Column(db.Integer, default=0)
    absent_count = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0.0)
    
    status = db.Column(db.String(20), default="Submitted")  # 'Submitted', 'Draft'
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    records = db.relationship('AttendanceRecord', backref='session', lazy='joined', cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint('date', 'subject_name', 'section', 'period', name='uq_session_date_subj_sec_period'),
    )


# =============================================================================
# ATTENDANCE RECORD MODEL (Per student per session)
# =============================================================================

class AttendanceRecord(db.Model):
    __tablename__ = 'attendance_records'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id', ondelete='CASCADE'), nullable=True)
    roll_no = db.Column(db.String(20), nullable=False, index=True)
    student_name = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(10), nullable=False)  # 'Present' or 'Absent'
    remarks = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        db.UniqueConstraint('session_id', 'roll_no', name='uq_session_student_record'),
    )


# =============================================================================
# SYSTEM SETTINGS MODEL
# =============================================================================

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


# =============================================================================
# LEGACY ATTENDANCE MODEL (Kept for backwards compatibility)
# =============================================================================

class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    roll_no = db.Column(db.String(20), nullable=False, index=True)
    date = db.Column(db.String(20), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False)


# =============================================================================
# DEFAULT STUDENT DATA
# =============================================================================

STUDENT_DATA = [
    ("256Q1A4317", "NOVALLAPALLIM INDRA SATYA PAVANI"),
    ("256Q1A4314", "MANDAPATI DURGA ASHOK KUMAR"),
    ("256Q1A4315", "TUBATI DINESH"),
    ("256Q1A4316", "MOLAKALAPALLI LAKSHMI GAYATRI"),
    ("25B21A4376", "PECHHETTI JESHMA SRI BHAVANI"),
    ("25B21A4353", "THIMMASERTHI SIVA RAO"),
    ("25B21A4346", "CHITTIBOINA DILEEP KUMAR"),
    ("25B21A4367", "PUSUNURI VISHNU VARDHAN"),
    ("25B21A4365", "BELGANA RAVI RAJA RAM"),
    ("25B21A4361", "SANGAPUREDDII YASWANTH"),
    ("25B21A4359", "MUVVA DURGA MAHESH"),
    ("25B21A4379", "BALAM SIVA KRISHNA"),
    ("25B21A4362", "LAVETI MANJUSHA"),
    ("25B21A4375", "KORASHIKA RUKMINI"),
    ("25B21A4351", "NAMBU TEJA SRI NAGENDRA"),
    ("25B21A4378", "KOPPULA ANURADHA MADHAVI"),
    ("25B21A4345", "GANTYADA SUSANTH DEVA HARSHA VARDHAN"),
    ("25B21A4364", "BOYINA MOKSHITHA"),
    ("25B21A4350", "SHAIK UMAR"),
    ("25B21A4352", "YENUGULA SUBASH CHANDHRA"),
    ("25B21A4377", "ARASADA DIMPUL PADMAJA RANI"),
    ("25B21A4371", "KOTHAPALLI CHARAN TEJ"),
    ("25B21A4348", "GEDELA CHINNI BABU"),
    ("25B21A4360", "MOHAMAD MUNAFAR REHAMAN"),
    ("25B21A4370", "DHARMASANAM SAI ROHITH"),
    ("25B21A4363", "KARAKA JYOTSHNA"),
    ("25B21A4374", "KUNCHE BHANU PAVAN TEJESH"),
    ("25B21A4344", "DALLI SAI"),
    ("25B21A4354", "CHAPPIDI MOHAN SATYA SAIKRISHNA"),
    ("25B21A4368", "CHAGALAMARRI NAFIL"),
    ("25B21A4381", "CHEEPURUPALLI YERNI SAI KRISHNA VANDITHA"),
    ("25B21A4358", "JAMPANA CHARAN"),
    ("25B21A4369", "CHOUDABOINA SUDHEER"),
    ("25B21A4380", "PUTLURI GEETANJALI"),
    ("25B21A4372", "GORLE PARIJATHA KALYANI"),
    ("25B21A4373", "PERIKA ENOSH KUMAR"),
    ("25B21A4349", "GALI TARUN SAI"),
    ("25B21A4355", "PUDI KALYANI"),
    ("25B21A4356", "KORNE MALEESWARI"),
    ("25B21A4347", "MITHIREDDY VAMSI"),
    ("25B21A4357", "BAIRISETTY YOGESWAR RAO"),
]

DEFAULT_SUBJECTS = [
    ("CS401", "Data Structures", "CAI", "Semester 3"),
    ("CS402", "Operating Systems", "CAI", "Semester 3"),
    ("AI401", "Artificial Intelligence & ML", "CAI", "Semester 3"),
    ("CS403", "Database Management Systems", "CAI", "Semester 3"),
    ("CS404", "Web Technologies", "CAI", "Semester 3"),
    ("CS405", "Computer Networks", "CAI", "Semester 3"),
]

DEFAULT_SECTIONS = [
    ("CAI-A", "CAI", "2nd Year"),
    ("CAI-B", "CAI", "2nd Year"),
    ("CSE-A", "CSE", "2nd Year"),
    ("ECE-A", "ECE", "2nd Year"),
]


# =============================================================================
# TIMETABLE & PERIOD MODEL (CTPO Period Management)
# =============================================================================

class TimetablePeriod(db.Model):
    __tablename__ = 'timetable_periods'

    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(20), nullable=False, index=True)  # Monday, Tuesday, Wednesday, Thursday, Friday, Saturday
    period_number = db.Column(db.String(10), nullable=False, index=True)  # '1', '2', '3', '4', '5', '6', '7', '8'
    start_time = db.Column(db.String(20), nullable=False, default="09:00 AM")
    end_time = db.Column(db.String(20), nullable=False, default="09:50 AM")
    subject_code = db.Column(db.String(20), nullable=True)
    subject_name = db.Column(db.String(100), nullable=False)
    section = db.Column(db.String(50), nullable=False, default="CAI-A", index=True)
    faculty_name = db.Column(db.String(120), nullable=False, default="Faculty Incharge")
    room = db.Column(db.String(50), nullable=True, default="Room 301")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        db.UniqueConstraint('day_of_week', 'period_number', 'section', name='uq_day_period_section'),
    )


PERIOD_TIMINGS = {
    "1": ("09:00 AM", "09:50 AM"),
    "2": ("09:50 AM", "10:40 AM"),
    "3": ("10:50 AM", "11:40 AM"),
    "4": ("11:40 AM", "12:30 PM"),
    "5": ("01:20 PM", "02:10 PM"),
    "6": ("02:10 PM", "03:00 PM"),
    "7": ("03:00 PM", "03:50 PM"),
    "8": ("03:50 PM", "04:40 PM"),
}

DEFAULT_TIMETABLE = [
    # Monday
    ("Monday", "1", "CS401", "Data Structures", "CAI-A", "Dr. A. Sharma", "Room 301"),
    ("Monday", "2", "AI401", "Artificial Intelligence & ML", "CAI-A", "Prof. K. Rajesh", "Room 301"),
    ("Monday", "3", "CS402", "Operating Systems", "CAI-A", "Dr. M. Sravanthi", "Room 301"),
    ("Monday", "4", "CS403", "Database Management Systems", "CAI-A", "Prof. P. Suresh", "Room 301"),
    ("Monday", "5", "CS404", "Web Technologies", "CAI-A", "Dr. V. Prasad", "Lab 2"),
    ("Monday", "6", "CS404", "Web Technologies", "CAI-A", "Dr. V. Prasad", "Lab 2"),
    ("Monday", "7", "CS405", "Computer Networks", "CAI-A", "Prof. R. Kumar", "Room 301"),
    ("Monday", "8", "AI401", "AI Mentorship & Seminar", "CAI-A", "Faculty Incharge", "Room 301"),

    # Tuesday
    ("Tuesday", "1", "AI401", "Artificial Intelligence & ML", "CAI-A", "Prof. K. Rajesh", "Room 301"),
    ("Tuesday", "2", "CS401", "Data Structures", "CAI-A", "Dr. A. Sharma", "Room 301"),
    ("Tuesday", "3", "CS405", "Computer Networks", "CAI-A", "Prof. R. Kumar", "Room 301"),
    ("Tuesday", "4", "CS402", "Operating Systems", "CAI-A", "Dr. M. Sravanthi", "Room 301"),
    ("Tuesday", "5", "CS403", "DBMS Lab", "CAI-A", "Prof. P. Suresh", "Lab 1"),
    ("Tuesday", "6", "CS403", "DBMS Lab", "CAI-A", "Prof. P. Suresh", "Lab 1"),
    ("Tuesday", "7", "CS404", "Web Technologies", "CAI-A", "Dr. V. Prasad", "Room 301"),
    ("Tuesday", "8", "CS401", "Tutorial & Doubt Clearing", "CAI-A", "Dr. A. Sharma", "Room 301"),

    # Wednesday
    ("Wednesday", "1", "CS403", "Database Management Systems", "CAI-A", "Prof. P. Suresh", "Room 301"),
    ("Wednesday", "2", "CS405", "Computer Networks", "CAI-A", "Prof. R. Kumar", "Room 301"),
    ("Wednesday", "3", "CS401", "Data Structures", "CAI-A", "Dr. A. Sharma", "Room 301"),
    ("Wednesday", "4", "AI401", "Artificial Intelligence & ML", "CAI-A", "Prof. K. Rajesh", "Room 301"),
    ("Wednesday", "5", "CS401", "Data Structures Lab", "CAI-A", "Dr. A. Sharma", "Lab 3"),
    ("Wednesday", "6", "CS401", "Data Structures Lab", "CAI-A", "Dr. A. Sharma", "Lab 3"),
    ("Wednesday", "7", "CS402", "Operating Systems", "CAI-A", "Dr. M. Sravanthi", "Room 301"),
    ("Wednesday", "8", "AI401", "Coding Practice Session", "CAI-A", "Faculty Incharge", "Lab 3"),

    # Thursday
    ("Thursday", "1", "CS402", "Operating Systems", "CAI-A", "Dr. M. Sravanthi", "Room 301"),
    ("Thursday", "2", "CS404", "Web Technologies", "CAI-A", "Dr. V. Prasad", "Room 301"),
    ("Thursday", "3", "AI401", "Artificial Intelligence & ML", "CAI-A", "Prof. K. Rajesh", "Room 301"),
    ("Thursday", "4", "CS401", "Data Structures", "CAI-A", "Dr. A. Sharma", "Room 301"),
    ("Thursday", "5", "CS405", "Networks Lab", "CAI-A", "Prof. R. Kumar", "Lab 2"),
    ("Thursday", "6", "CS405", "Networks Lab", "CAI-A", "Prof. R. Kumar", "Lab 2"),
    ("Thursday", "7", "CS403", "Database Management Systems", "CAI-A", "Prof. P. Suresh", "Room 301"),
    ("Thursday", "8", "CS404", "Technical Seminar", "CAI-A", "Faculty Incharge", "Room 301"),

    # Friday
    ("Friday", "1", "CS405", "Computer Networks", "CAI-A", "Prof. R. Kumar", "Room 301"),
    ("Friday", "2", "CS403", "Database Management Systems", "CAI-A", "Prof. P. Suresh", "Room 301"),
    ("Friday", "3", "CS404", "Web Technologies", "CAI-A", "Dr. V. Prasad", "Room 301"),
    ("Friday", "4", "CS402", "Operating Systems", "CAI-A", "Dr. M. Sravanthi", "Room 301"),
    ("Friday", "5", "AI401", "AI & ML Hands-on Lab", "CAI-A", "Prof. K. Rajesh", "Lab 1"),
    ("Friday", "6", "AI401", "AI & ML Hands-on Lab", "CAI-A", "Prof. K. Rajesh", "Lab 1"),
    ("Friday", "7", "CS401", "Data Structures", "CAI-A", "Dr. A. Sharma", "Room 301"),
    ("Friday", "8", "AI401", "Weekly Review & Feedback", "CAI-A", "Faculty Incharge", "Room 301"),

    # Saturday
    ("Saturday", "1", "CS401", "Data Structures", "CAI-A", "Dr. A. Sharma", "Room 301"),
    ("Saturday", "2", "AI401", "Artificial Intelligence & ML", "CAI-A", "Prof. K. Rajesh", "Room 301"),
    ("Saturday", "3", "CS402", "Operating Systems", "CAI-A", "Dr. M. Sravanthi", "Room 301"),
    ("Saturday", "4", "CS403", "Database Management Systems", "CAI-A", "Prof. P. Suresh", "Room 301"),
]
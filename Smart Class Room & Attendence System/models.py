from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# ---------------- STUDENT ----------------

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    roll_no = db.Column(
        db.String(20),
        unique=True,
        nullable=False
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )


# ---------------- ATTENDANCE ----------------

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    roll_no = db.Column(
        db.String(20),
        nullable=False
    )

    date = db.Column(
        db.String(20),
        nullable=False
    )

    status = db.Column(
        db.String(10),
        nullable=False
    )


# ---------------- STUDENT DATA ----------------

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
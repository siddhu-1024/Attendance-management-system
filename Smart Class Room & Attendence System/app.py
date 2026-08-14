from datetime import datetime
from flask import Flask, jsonify
from flask import redirect, render_template
from flask import request, url_for

from models import db, Student, Attendance
from models import STUDENT_DATA


app = Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///smart_classroom.db"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


# ---------- DATABASE ----------

with app.app_context():

    db.create_all()

    if not Student.query.first():

        for roll, name in STUDENT_DATA:

            db.session.add(
                Student(
                    roll_no=roll,
                    name=name
                )
            )

        db.session.commit()


# ---------- LOGIN ----------

@app.route("/")
def login_page():

    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def handle_login():

    department = request.form.get("department")
    password = request.form.get("password")

    if password == "CAIH@24-29" and department:

        return redirect(
            url_for("dashboard_page")
        )

    return redirect(
        url_for("login_page")
    )


# ---------- DASHBOARD ----------

@app.route("/dashboard")
def dashboard_page():

    return render_template(
        "dashboard.html"
    )


# ---------- STUDENTS ----------

@app.route("/api/students")
def get_students():

    students = Student.query.all()

    data = []

    for student in students:

        data.append({
            "roll_no": student.roll_no,
            "name": student.name
        })

    return jsonify(data)


# ---------- SAVE ATTENDANCE ----------

@app.route(
    "/api/attendance/bulk",
    methods=["POST"]
)
def save_attendance():

    data = request.json
    records = data.get("records", {})

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    for roll_no, status in records.items():

        old = Attendance.query.filter_by(
            roll_no=roll_no,
            date=today
        ).first()

        if old:

            old.status = status

        else:

            db.session.add(
                Attendance(
                    roll_no=roll_no,
                    date=today,
                    status=status
                )
            )

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Attendance saved"
    })


# ---------- ATTENDANCE SUMMARY ----------

@app.route("/api/attendance/summary")
def attendance_summary():

    students = Student.query.all()

    result = []

    for student in students:

        records = Attendance.query.filter_by(
            roll_no=student.roll_no
        ).all()

        total = len(records)

        present = sum(
            1 for r in records
            if r.status == "Present"
        )

        absent = total - present

        percentage = (
            round((present / total) * 100, 1)
            if total else 0
        )

        result.append({
            "roll_no": student.roll_no,
            "name": student.name,
            "total": total,
            "present": present,
            "absent": absent,
            "percentage": percentage
        })

    return jsonify(result)


# ---------- DASHBOARD STATS ----------

@app.route("/api/dashboard")
def dashboard_stats():

    records = Attendance.query.all()

    total = len(records)

    present = sum(
        1 for r in records
        if r.status == "Present"
    )

    absent = sum(
        1 for r in records
        if r.status == "Absent"
    )

    students = Student.query.count()

    percentage = (
        round((present / total) * 100, 1)
        if total else 0
    )

    return jsonify({
        "students": students,
        "total_records": total,
        "present": present,
        "absent": absent,
        "percentage": percentage
    })


# ---------- LOW ATTENDANCE ----------

@app.route("/api/attendance/low")
def low_attendance():

    students = Student.query.all()

    low_students = []

    for student in students:

        records = Attendance.query.filter_by(
            roll_no=student.roll_no
        ).all()

        total = len(records)

        if total == 0:
            continue

        present = sum(
            1 for r in records
            if r.status == "Present"
        )

        percentage = (
            present / total
        ) * 100

        if percentage < 75:

            low_students.append({
                "roll_no": student.roll_no,
                "name": student.name,
                "percentage": round(
                    percentage, 1
                )
            })

    return jsonify(low_students)


# ---------- RUN ----------

if __name__ == "__main__":

    app.run(debug=True)
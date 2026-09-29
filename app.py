import os
from datetime import datetime, timezone
from functools import wraps
from flask import (
    Flask, jsonify, redirect, render_template,
    request, url_for, session, send_file, Response
)
from models import (
    db, Student, Subject, Section, AttendanceSession,
    AttendanceRecord, SystemSetting, User, Attendance,
    TimetablePeriod, PERIOD_TIMINGS, DEFAULT_TIMETABLE,
    STUDENT_DATA, DEFAULT_SUBJECTS, DEFAULT_SECTIONS
)
import export_utils


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "smart-classroom-production-key-2026-cai")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///smart_classroom.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


# =============================================================================
# AUTHENTICATION HELPERS & DECORATORS
# =============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session and "student_id" not in session and not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized. Please log in."}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Forbidden. Admin privilege required."}), 403
            return redirect(url_for("dashboard_page"))
        return f(*args, **kwargs)
    return decorated_function


def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") not in ["admin", "faculty", "ctpo"]:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Forbidden. Faculty/CTPO/Admin privilege required."}), 403
            return redirect(url_for("dashboard_page"))
        return f(*args, **kwargs)
    return decorated_function


def ctpo_or_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") not in ["admin", "ctpo", "faculty"]:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Forbidden. CTPO or Admin privilege required."}), 403
            return redirect(url_for("dashboard_page"))
        return f(*args, **kwargs)
    return decorated_function


def get_setting_value(key, default_value=""):
    setting = SystemSetting.query.filter_by(key=key).first()
    return setting.value if setting else default_value


def get_low_attendance_threshold():
    try:
        val = get_setting_value("low_attendance_threshold", "75.0")
        return float(val)
    except Exception:
        return 75.0


def get_college_name():
    return get_setting_value("college_name", "Smart Classroom College of Engineering & Technology")


# =============================================================================
# DATABASE INITIALIZATION & AUTO-MIGRATION
# =============================================================================

with app.app_context():
    db.create_all()

    # 1. Initialize System Settings
    default_settings = [
        ("low_attendance_threshold", "75.0", "Threshold percentage below which attendance is flagged as low"),
        ("default_attendance_state", "Present", "Default attendance state for newly loaded sessions (Present/Absent)"),
        ("college_name", "Smart Classroom College of Engineering & Technology", "Institution Name on Reports"),
        ("department_name", "Department of Computer Science & AI (CAI)", "Primary Academic Department"),
    ]
    for key, val, desc in default_settings:
        if not SystemSetting.query.filter_by(key=key).first():
            db.session.add(SystemSetting(key=key, value=val, description=desc))

    # 2. Initialize Users (Admin, Faculty, CTPO)
    if not User.query.filter_by(username="admin").first():
        admin_user = User(
            username="admin",
            full_name="Department Head / Admin",
            email="admin.cai@college.edu",
            department="CAI",
            role="admin"
        )
        admin_user.set_password("admin123")
        db.session.add(admin_user)

    if not User.query.filter_by(username="faculty").first():
        faculty_user = User(
            username="faculty",
            full_name="Faculty Incharge",
            email="faculty.cai@college.edu",
            department="CAI",
            role="faculty"
        )
        faculty_user.set_password("CAIH@24-29")
        db.session.add(faculty_user)

    if not User.query.filter_by(username="ctpo").first():
        ctpo_user = User(
            username="ctpo",
            full_name="CTPO - Timetable & Period Officer",
            email="ctpo.cai@college.edu",
            department="CAI",
            role="ctpo"
        )
        ctpo_user.set_password("ctpo123")
        db.session.add(ctpo_user)

    # 3. Initialize Subjects
    for code, name, dept, sem in DEFAULT_SUBJECTS:
        if not Subject.query.filter_by(code=code).first():
            db.session.add(Subject(code=code, name=name, department=dept, semester=sem))

    # 4. Initialize Sections
    for name, dept, year in DEFAULT_SECTIONS:
        if not Section.query.filter_by(name=name).first():
            db.session.add(Section(name=name, department=dept, year=year))

    # 5. Initialize Students (Roster of 41 students with default passwords)
    for roll, name in STUDENT_DATA:
        st = Student.query.filter_by(roll_no=roll).first()
        if not st:
            st = Student(
                roll_no=roll,
                name=name,
                department="CAI",
                section="CAI-A",
                is_active=True
            )
            st.set_password("student123")
            db.session.add(st)
        elif not st.password_hash:
            st.set_password("student123")

    # 6. Initialize Default Timetable Periods (CTPO Schedule)
    if not TimetablePeriod.query.first():
        for day, period_num, code, name, sec, fac, room in DEFAULT_TIMETABLE:
            start_t, end_t = PERIOD_TIMINGS.get(period_num, ("09:00 AM", "09:50 AM"))
            db.session.add(TimetablePeriod(
                day_of_week=day,
                period_number=period_num,
                start_time=start_t,
                end_time=end_t,
                subject_code=code,
                subject_name=name,
                section=sec,
                faculty_name=fac,
                room=room
            ))

    # 7. Migrate legacy attendance rows
    legacy_dates = db.session.query(Attendance.date).distinct().all()
    for (legacy_date,) in legacy_dates:
        existing_session = AttendanceSession.query.filter_by(
            date=legacy_date,
            subject_name="Data Structures",
            section="CAI-A",
            period="1"
        ).first()

        if not existing_session:
            legacy_records = Attendance.query.filter_by(date=legacy_date).all()
            if legacy_records:
                total = len(legacy_records)
                present_count = sum(1 for r in legacy_records if r.status == "Present")
                absent_count = total - present_count
                pct = round((present_count / total) * 100, 2) if total else 0.0

                new_session = AttendanceSession(
                    date=legacy_date,
                    subject_name="Data Structures",
                    section="CAI-A",
                    period="1",
                    topic="Data Structures Lecture",
                    faculty_name="Faculty Incharge",
                    total_students=total,
                    present_count=present_count,
                    absent_count=absent_count,
                    percentage=pct,
                    status="Submitted"
                )
                db.session.add(new_session)
                db.session.flush()

                for lr in legacy_records:
                    st = Student.query.filter_by(roll_no=lr.roll_no).first()
                    st_name = st.name if st else lr.roll_no
                    db.session.add(AttendanceRecord(
                        session_id=new_session.id,
                        student_id=st.id if st else None,
                        roll_no=lr.roll_no,
                        student_name=st_name,
                        status=lr.status
                    ))

    db.session.commit()


# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================

@app.route("/")
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("dashboard_page"))
    return render_template("login.html")


@app.route("/api/login", methods=["POST"])
def handle_login():
    data = request.json if request.is_json else request.form
    login_type = data.get("login_type", "").strip()
    department = data.get("department", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    student_roll = data.get("studentRoll", "").strip()
    student_pwd = data.get("studentPassword", "").strip()

    # 1. Dedicated Student Login
    if login_type == "student" or student_roll:
        roll_to_check = (student_roll or username).strip()
        pwd_to_check = (student_pwd or password).strip()

        if not roll_to_check:
            msg = "Please enter your Student Roll Number."
            if request.is_json:
                return jsonify({"success": False, "message": msg}), 400
            return render_template("login.html", error=msg)

        student = Student.query.filter(db.func.upper(Student.roll_no) == roll_to_check.upper()).first()
        if student and (student.check_password(pwd_to_check) or pwd_to_check.upper() == student.roll_no.upper()):
            session.clear()
            session["student_id"] = student.id
            session["roll_no"] = student.roll_no
            session["username"] = student.roll_no
            session["full_name"] = student.name
            session["role"] = "student"
            session["department"] = student.department
            session["section"] = student.section
            session["logged_in"] = True

            resp_payload = {
                "success": True,
                "message": f"Welcome, {student.name}",
                "user": {
                    "username": student.roll_no,
                    "roll_no": student.roll_no,
                    "full_name": student.name,
                    "role": "student",
                    "department": student.department,
                    "section": student.section
                },
                "redirect": url_for("dashboard_page")
            }
            if request.is_json:
                return jsonify(resp_payload)
            return redirect(url_for("dashboard_page"))
        else:
            msg = "Invalid credentials. Use your Roll Number for both Username and Password."
            if request.is_json:
                return jsonify({"success": False, "message": msg}), 401
            return render_template("login.html", error=msg)

    # 2. CTPO Login
    if username.lower() == "ctpo" or login_type == "ctpo" or department == "CTPO":
        ctpo_user = User.query.filter_by(username="ctpo").first()
        if (password == "ctpo123") or (ctpo_user and ctpo_user.check_password(password)):
            session.clear()
            session["user_id"] = ctpo_user.id if ctpo_user else 999
            session["username"] = "ctpo"
            session["full_name"] = ctpo_user.full_name if ctpo_user else "CTPO Incharge"
            session["role"] = "ctpo"
            session["department"] = "CAI"
            session["logged_in"] = True

            resp_payload = {
                "success": True,
                "message": "CTPO Login successful",
                "user": {
                    "username": "ctpo",
                    "full_name": session["full_name"],
                    "role": "ctpo",
                    "department": "CAI"
                },
                "redirect": url_for("dashboard_page")
            }
            if request.is_json:
                return jsonify(resp_payload)
            return redirect(url_for("dashboard_page"))

    # 3. Fallback Student check by roll number if entered in common username field
    if username:
        student = Student.query.filter(db.func.upper(Student.roll_no) == username.upper()).first()
        if student and (student.check_password(password) or password.upper() == student.roll_no.upper()):
            session.clear()
            session["student_id"] = student.id
            session["roll_no"] = student.roll_no
            session["username"] = student.roll_no
            session["full_name"] = student.name
            session["role"] = "student"
            session["department"] = student.department
            session["section"] = student.section
            session["logged_in"] = True

            resp_payload = {
                "success": True,
                "message": f"Welcome, {student.name}",
                "user": {
                    "username": student.roll_no,
                    "roll_no": student.roll_no,
                    "full_name": student.name,
                    "role": "student",
                    "department": student.department,
                    "section": student.section
                },
                "redirect": url_for("dashboard_page")
            }
            if request.is_json:
                return jsonify(resp_payload)
            return redirect(url_for("dashboard_page"))

    # 4. User Table Login (Faculty, Admin, Staff)
    user = None
    if username:
        user = User.query.filter_by(username=username).first()

    # Department-based quick login (default faculty password: CAIH@24-29)
    if not user and department:
        if password == "CAIH@24-29":
            user = User.query.filter_by(department=department, role="faculty").first()
            if not user:
                user = User.query.filter_by(role="faculty").first()

    if user and user.check_password(password):
        session.clear()
        session["user_id"] = user.id
        session["username"] = user.username
        session["full_name"] = user.full_name
        session["role"] = user.role
        session["department"] = user.department
        session["logged_in"] = True

        if request.is_json:
            return jsonify({
                "success": True,
                "message": "Login successful",
                "user": {
                    "username": user.username,
                    "full_name": user.full_name,
                    "role": user.role,
                    "department": user.department
                },
                "redirect": url_for("dashboard_page")
            })
        return redirect(url_for("dashboard_page"))

    # Admin direct login
    if username == "admin" and password == "admin123":
        admin = User.query.filter_by(username="admin").first()
        if admin:
            session.clear()
            session["user_id"] = admin.id
            session["username"] = admin.username
            session["full_name"] = admin.full_name
            session["role"] = "admin"
            session["department"] = admin.department
            session["logged_in"] = True
            if request.is_json:
                return jsonify({"success": True, "redirect": url_for("dashboard_page")})
            return redirect(url_for("dashboard_page"))

    if request.is_json:
        return jsonify({"success": False, "message": "Invalid username or password"}), 401

    return render_template("login.html", error="Invalid credentials. Please verify your login details.")


@app.route("/logout")
@app.route("/api/logout", methods=["GET", "POST"])
def handle_logout():
    session.clear()
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"success": True, "redirect": url_for("login_page")})
    return redirect(url_for("login_page"))


@app.route("/api/auth/me")
@login_required
def get_current_user():
    threshold = get_low_attendance_threshold()
    college_name = get_college_name()
    dept_name = get_setting_value("department_name", "Department of Computer Science & AI (CAI)")
    default_state = get_setting_value("default_attendance_state", "Present")

    user_info = {
        "id": session.get("user_id") or session.get("student_id"),
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "role": session.get("role"),
        "department": session.get("department"),
        "section": session.get("section"),
        "roll_no": session.get("roll_no"),
        "is_student": (session.get("role") == "student"),
        "is_ctpo": (session.get("role") == "ctpo"),
        "is_admin": (session.get("role") == "admin")
    }

    return jsonify({
        "user": user_info,
        "settings": {
            "low_attendance_threshold": threshold,
            "college_name": college_name,
            "department_name": dept_name,
            "default_attendance_state": default_state
        }
    })



# =============================================================================
# DASHBOARD & MAIN PAGES
# =============================================================================

@app.route("/dashboard")
@login_required
def dashboard_page():
    return render_template("dashboard.html")


# =============================================================================
# SETTINGS & METADATA APIS
# =============================================================================

@app.route("/api/settings", methods=["GET", "POST"])
@login_required
def manage_settings():
    if request.method == "POST":
        data = request.json or {}
        if "low_attendance_threshold" in data:
            try:
                thresh_val = float(data["low_attendance_threshold"])
                if thresh_val < 0 or thresh_val > 100:
                    return jsonify({"success": False, "message": "Threshold must be between 0 and 100"}), 400
                st = SystemSetting.query.filter_by(key="low_attendance_threshold").first()
                if st:
                    st.value = str(thresh_val)
                else:
                    db.session.add(SystemSetting(key="low_attendance_threshold", value=str(thresh_val)))
            except ValueError:
                return jsonify({"success": False, "message": "Invalid threshold number"}), 400

        if "default_attendance_state" in data:
            state_val = "Present" if data["default_attendance_state"] == "Present" else "Absent"
            st = SystemSetting.query.filter_by(key="default_attendance_state").first()
            if st:
                st.value = state_val
            else:
                db.session.add(SystemSetting(key="default_attendance_state", value=state_val))

        if "college_name" in data and data["college_name"].strip():
            c_val = data["college_name"].strip()
            st = SystemSetting.query.filter_by(key="college_name").first()
            if st:
                st.value = c_val
            else:
                db.session.add(SystemSetting(key="college_name", value=c_val))

        if "department_name" in data and data["department_name"].strip():
            d_val = data["department_name"].strip()
            st = SystemSetting.query.filter_by(key="department_name").first()
            if st:
                st.value = d_val
            else:
                db.session.add(SystemSetting(key="department_name", value=d_val))

        db.session.commit()
        return jsonify({"success": True, "message": "Settings updated successfully"})

    settings = SystemSetting.query.all()
    res = {s.key: s.value for s in settings}
    res["low_attendance_threshold"] = float(res.get("low_attendance_threshold", 75.0))
    return jsonify(res)


@app.route("/api/subjects", methods=["GET", "POST"])
@login_required
def manage_subjects():
    if request.method == "POST":
        data = request.json or {}
        code = data.get("code", "").strip().upper()
        name = data.get("name", "").strip()
        dept = data.get("department", "CAI").strip()
        sem = data.get("semester", "Semester 3").strip()

        if not code or not name:
            return jsonify({"success": False, "message": "Subject code and name are required"}), 400

        if Subject.query.filter_by(code=code).first():
            return jsonify({"success": False, "message": f"Subject code '{code}' already exists"}), 400

        new_subj = Subject(code=code, name=name, department=dept, semester=sem)
        db.session.add(new_subj)
        db.session.commit()
        return jsonify({"success": True, "message": "Subject added successfully", "id": new_subj.id})

    subjects = Subject.query.order_by(Subject.name).all()
    return jsonify([{
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "department": s.department,
        "semester": s.semester
    } for s in subjects])


@app.route("/api/sections", methods=["GET", "POST"])
@login_required
def manage_sections():
    if request.method == "POST":
        data = request.json or {}
        name = data.get("name", "").strip().upper()
        dept = data.get("department", "CAI").strip()
        year = data.get("year", "2nd Year").strip()

        if not name:
            return jsonify({"success": False, "message": "Section name is required"}), 400

        if Section.query.filter_by(name=name).first():
            return jsonify({"success": False, "message": f"Section '{name}' already exists"}), 400

        new_sec = Section(name=name, department=dept, year=year)
        db.session.add(new_sec)
        db.session.commit()
        return jsonify({"success": True, "message": "Section added successfully", "id": new_sec.id})

    sections = Section.query.order_by(Section.name).all()
    return jsonify([{
        "id": sec.id,
        "name": sec.name,
        "department": sec.department,
        "year": sec.year
    } for sec in sections])


# =============================================================================
# TIMETABLE & PERIOD MANAGEMENT APIS (CTPO Period Control)
# =============================================================================

@app.route("/api/timetable", methods=["GET", "POST"])
@login_required
def manage_timetable():
    if request.method == "POST":
        if session.get("role") not in ["admin", "ctpo", "faculty"]:
            return jsonify({"success": False, "message": "Only CTPO/Admin can edit periods & timetable"}), 403

        data = request.json or {}
        day = data.get("day_of_week", "").strip()
        period_num = str(data.get("period_number", "1")).strip()
        subject_name = data.get("subject_name", "").strip()
        subject_code = data.get("subject_code", "").strip()
        section = data.get("section", "CAI-A").strip()
        faculty_name = data.get("faculty_name", "Faculty Incharge").strip()
        room = data.get("room", "Room 301").strip()
        start_time = data.get("start_time", "").strip()
        end_time = data.get("end_time", "").strip()

        if not day or not period_num or not subject_name:
            return jsonify({"success": False, "message": "Day, period number, and subject name are required"}), 400

        if not start_time or not end_time:
            def_start, def_end = PERIOD_TIMINGS.get(period_num, ("09:00 AM", "09:50 AM"))
            start_time = start_time or def_start
            end_time = end_time or def_end

        # Check existing entry for same day, period, section
        entry = TimetablePeriod.query.filter_by(
            day_of_week=day,
            period_number=period_num,
            section=section
        ).first()

        if entry:
            entry.subject_name = subject_name
            entry.subject_code = subject_code
            entry.faculty_name = faculty_name
            entry.room = room
            entry.start_time = start_time
            entry.end_time = end_time
            entry.updated_at = datetime.now()
            db.session.commit()
            return jsonify({
                "success": True,
                "message": f"Period {period_num} ({day}) updated successfully",
                "period": {
                    "id": entry.id,
                    "day_of_week": entry.day_of_week,
                    "period_number": entry.period_number,
                    "start_time": entry.start_time,
                    "end_time": entry.end_time,
                    "subject_name": entry.subject_name,
                    "subject_code": entry.subject_code,
                    "section": entry.section,
                    "faculty_name": entry.faculty_name,
                    "room": entry.room
                }
            })
        else:
            new_entry = TimetablePeriod(
                day_of_week=day,
                period_number=period_num,
                start_time=start_time,
                end_time=end_time,
                subject_name=subject_name,
                subject_code=subject_code,
                section=section,
                faculty_name=faculty_name,
                room=room
            )
            db.session.add(new_entry)
            db.session.commit()
            return jsonify({
                "success": True,
                "message": f"Period {period_num} ({day}) added successfully",
                "period": {
                    "id": new_entry.id,
                    "day_of_week": new_entry.day_of_week,
                    "period_number": new_entry.period_number,
                    "start_time": new_entry.start_time,
                    "end_time": new_entry.end_time,
                    "subject_name": new_entry.subject_name,
                    "subject_code": new_entry.subject_code,
                    "section": new_entry.section,
                    "faculty_name": new_entry.faculty_name,
                    "room": new_entry.room
                }
            })

    # GET timetable
    day_filter = request.args.get("day")
    section_filter = request.args.get("section", "CAI-A")
    period_filter = request.args.get("period")

    query = TimetablePeriod.query
    if section_filter and section_filter != "all":
        query = query.filter_by(section=section_filter)
    if day_filter and day_filter != "all":
        query = query.filter_by(day_of_week=day_filter)
    if period_filter:
        query = query.filter_by(period_number=period_filter)

    periods = query.order_by(TimetablePeriod.day_of_week, TimetablePeriod.period_number).all()

    # Sort days naturally: Monday -> Saturday
    day_order = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4, "Friday": 5, "Saturday": 6, "Sunday": 7}
    sorted_periods = sorted(periods, key=lambda p: (day_order.get(p.day_of_week, 99), int(p.period_number) if p.period_number.isdigit() else 99))

    return jsonify({
        "success": True,
        "periods": [{
            "id": p.id,
            "day_of_week": p.day_of_week,
            "period_number": p.period_number,
            "start_time": p.start_time,
            "end_time": p.end_time,
            "subject_code": p.subject_code or "",
            "subject_name": p.subject_name,
            "section": p.section,
            "faculty_name": p.faculty_name,
            "room": p.room or "Room 301"
        } for p in sorted_periods],
        "period_timings": PERIOD_TIMINGS
    })


@app.route("/api/timetable/<int:period_id>", methods=["PUT", "DELETE"])
@login_required
def update_or_delete_timetable_period(period_id):
    if session.get("role") not in ["admin", "ctpo", "faculty"]:
        return jsonify({"success": False, "message": "Forbidden. CTPO or Admin privilege required."}), 403

    entry = db.session.get(TimetablePeriod, period_id)
    if not entry:
        return jsonify({"success": False, "message": "Timetable period not found"}), 404

    if request.method == "DELETE":
        db.session.delete(entry)
        db.session.commit()
        return jsonify({"success": True, "message": "Period deleted successfully"})

    data = request.json or {}
    if "subject_name" in data and data["subject_name"].strip():
        entry.subject_name = data["subject_name"].strip()
    if "subject_code" in data:
        entry.subject_code = data["subject_code"].strip()
    if "faculty_name" in data and data["faculty_name"].strip():
        entry.faculty_name = data["faculty_name"].strip()
    if "room" in data:
        entry.room = data["room"].strip()
    if "start_time" in data and data["start_time"].strip():
        entry.start_time = data["start_time"].strip()
    if "end_time" in data and data["end_time"].strip():
        entry.end_time = data["end_time"].strip()
    if "day_of_week" in data and data["day_of_week"].strip():
        entry.day_of_week = data["day_of_week"].strip()
    if "period_number" in data and str(data["period_number"]).strip():
        entry.period_number = str(data["period_number"]).strip()

    entry.updated_at = datetime.now()
    db.session.commit()
    return jsonify({
        "success": True,
        "message": "Period updated successfully",
        "period": {
            "id": entry.id,
            "day_of_week": entry.day_of_week,
            "period_number": entry.period_number,
            "start_time": entry.start_time,
            "end_time": entry.end_time,
            "subject_code": entry.subject_code or "",
            "subject_name": entry.subject_name,
            "section": entry.section,
            "faculty_name": entry.faculty_name,
            "room": entry.room or "Room 301"
        }
    })


@app.route("/api/periods/for-time", methods=["GET"])
@login_required
def get_subjects_for_period_time():
    """
    Returns the mapped subject and all available subjects for a specific period & day
    so CTPO can instantly list and select subjects for that time.
    """
    day_val = request.args.get("day", "").strip()
    period_val = str(request.args.get("period", "1")).strip()
    section_val = request.args.get("section", "CAI-A").strip()
    date_val = request.args.get("date", "").strip()

    # Determine weekday if date is provided
    if date_val and not day_val:
        try:
            dt = datetime.strptime(date_val, "%Y-%m-%d")
            day_val = dt.strftime("%A")
        except ValueError:
            day_val = "Monday"

    if not day_val:
        day_val = datetime.now().strftime("%A")

    # Look up scheduled period
    scheduled = TimetablePeriod.query.filter_by(
        day_of_week=day_val,
        period_number=period_val,
        section=section_val
    ).first()

    # All registered subjects
    all_subjects = Subject.query.order_by(Subject.name).all()
    subjects_list = [{
        "id": s.id,
        "code": s.code,
        "name": s.name,
        "department": s.department,
        "semester": s.semester
    } for s in all_subjects]

    timing = PERIOD_TIMINGS.get(period_val, ("09:00 AM", "09:50 AM"))

    return jsonify({
        "success": True,
        "day": day_val,
        "period": period_val,
        "section": section_val,
        "timing": f"{timing[0]} - {timing[1]}",
        "start_time": timing[0],
        "end_time": timing[1],
        "scheduled_subject": scheduled.subject_name if scheduled else "",
        "scheduled_code": scheduled.subject_code if scheduled else "",
        "scheduled_faculty": scheduled.faculty_name if scheduled else "Faculty Incharge",
        "room": scheduled.room if scheduled else "Room 301",
        "all_subjects": subjects_list
    })


# =============================================================================
# DAY-WISE ATTENDANCE CALCULATION ENGINE
# =============================================================================

def get_all_students_day_wise_stats(student_list=None):
    """
    Calculate Day-Wise attendance stats for all (or given) students in bulk.
    Full Day Only rule:
    - On each unique working date, a student is Present (1.0) only if they attended ALL periods held on that date.
    - If they miss even 1 period on that date, they are considered Absent (0.0) for that day.
    - Overall Day-Wise Percentage = (Present Days / Total Working Days) * 100.
    """
    if student_list is None:
        student_list = Student.query.filter_by(is_active=True).all()

    roll_list = [s.roll_no for s in student_list]
    if not roll_list:
        return {}

    records = AttendanceRecord.query.filter(AttendanceRecord.roll_no.in_(roll_list)).all()

    # Map roll_no -> date_str -> {"total": 0, "present": 0}
    student_date_map = {r: {} for r in roll_list}
    student_class_counts = {r: {"total": 0, "present": 0} for r in roll_list}

    for r in records:
        sess = r.session
        d_str = sess.date if sess else (r.created_at.strftime("%Y-%m-%d") if r.created_at else datetime.now().strftime("%Y-%m-%d"))
        roll = r.roll_no

        if roll not in student_date_map:
            student_date_map[roll] = {}
            student_class_counts[roll] = {"total": 0, "present": 0}

        student_class_counts[roll]["total"] += 1
        if r.status == "Present":
            student_class_counts[roll]["present"] += 1

        if d_str not in student_date_map[roll]:
            student_date_map[roll][d_str] = {"total": 0, "present": 0}

        student_date_map[roll][d_str]["total"] += 1
        if r.status == "Present":
            student_date_map[roll][d_str]["present"] += 1

    stats_by_roll = {}
    for roll in roll_list:
        date_dict = student_date_map.get(roll, {})
        tot_days = len(date_dict)
        # Full Day Only: all periods on that date must be attended
        pres_days = sum(1 for d, info in date_dict.items() if info["present"] == info["total"] and info["total"] > 0)
        abs_days = tot_days - pres_days
        pct = round((pres_days / tot_days) * 100, 2) if tot_days > 0 else 0.0

        c_info = student_class_counts.get(roll, {"total": 0, "present": 0})

        stats_by_roll[roll] = {
            "total_days": tot_days,
            "present_days": pres_days,
            "absent_days": abs_days,
            "total_classes": c_info["total"],
            "present_classes": c_info["present"],
            "absent_classes": c_info["total"] - c_info["present"],
            "percentage": pct
        }

    return stats_by_roll


# =============================================================================
# STUDENTS & ROSTER APIS
# =============================================================================


@app.route("/api/students", methods=["GET", "POST"])
@login_required
def get_students():
    if request.method == "POST":
        if session.get("role") not in ["admin", "faculty", "ctpo"]:
            return jsonify({"success": False, "message": "Forbidden. Staff or Admin privilege required."}), 403

        data = request.json or {}
        roll_no = data.get("roll_no", "").strip().upper()
        name = data.get("name", "").strip().upper()
        dept = data.get("department", "CAI").strip()
        section = data.get("section", "CAI-A").strip()
        email = data.get("email", "").strip()

        if not roll_no or not name:
            return jsonify({"success": False, "message": "Roll number and student name are required"}), 400

        if Student.query.filter_by(roll_no=roll_no).first():
            return jsonify({"success": False, "message": f"Student with roll number {roll_no} already exists"}), 400

        new_student = Student(
            roll_no=roll_no,
            name=name,
            department=dept,
            section=section,
            email=email,
            is_active=True
        )
        new_student.set_password("student123")
        db.session.add(new_student)
        db.session.commit()
        return jsonify({"success": True, "message": "Student added successfully", "student": {
            "id": new_student.id,
            "roll_no": new_student.roll_no,
            "name": new_student.name
        }})

    section_filter = request.args.get("section")
    search_query = request.args.get("search", "").strip().lower()

    query = Student.query.filter_by(is_active=True)
    if section_filter:
        query = query.filter_by(section=section_filter)

    students = query.order_by(Student.roll_no).all()
    threshold = get_low_attendance_threshold()
    bulk_stats = get_all_students_day_wise_stats(students)

    data = []
    for student in students:
        if search_query:
            if search_query not in student.name.lower() and search_query not in student.roll_no.lower():
                continue

        st_stat = bulk_stats.get(student.roll_no, {
            "total_days": 0, "present_days": 0, "absent_days": 0,
            "total_classes": 0, "present_classes": 0, "absent_classes": 0,
            "percentage": 0.0
        })

        data.append({
            "id": student.id,
            "roll_no": student.roll_no,
            "name": student.name,
            "department": student.department,
            "section": student.section,
            "total_days": st_stat["total_days"],
            "present_days": st_stat["present_days"],
            "absent_days": st_stat["absent_days"],
            "total_classes": st_stat["total_classes"],
            "present_classes": st_stat["present_classes"],
            "absent_classes": st_stat["absent_classes"],
            "attendance_percentage": st_stat["percentage"],
            "is_low": (st_stat["percentage"] < threshold and st_stat["total_days"] > 0)
        })

    return jsonify(data)


@app.route("/api/students/<roll_no>", methods=["PUT", "DELETE"])
@login_required
def update_or_delete_student(roll_no):
    if session.get("role") not in ["admin", "faculty", "ctpo"]:
        return jsonify({"success": False, "message": "Forbidden. Staff or Admin privilege required."}), 403

    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    if request.method == "DELETE":
        AttendanceRecord.query.filter_by(roll_no=roll_no).delete()
        Attendance.query.filter_by(roll_no=roll_no).delete()
        db.session.delete(student)
        db.session.commit()
        return jsonify({"success": True, "message": f"Student {roll_no} deleted successfully"})

    data = request.json or {}
    if "name" in data and data["name"].strip():
        student.name = data["name"].strip().upper()
    if "section" in data:
        student.section = data["section"].strip()
    if "department" in data:
        student.department = data["department"].strip()
    if "email" in data:
        student.email = data["email"].strip()

    db.session.commit()
    return jsonify({"success": True, "message": "Student updated successfully"})


# =============================================================================
# ATTENDANCE MARKING & SAVING APIS
# =============================================================================

@app.route("/api/attendance/check", methods=["GET"])
@login_required
def check_existing_session():
    date_val = request.args.get("date", "").strip()
    subject_val = request.args.get("subject", "").strip()
    section_val = request.args.get("section", "").strip()
    period_val = str(request.args.get("period", "1")).strip()

    if not date_val or not subject_val or not section_val or not period_val:
        return jsonify({"exists": False})

    session_obj = AttendanceSession.query.filter_by(
        date=date_val,
        subject_name=subject_val,
        section=section_val,
        period=period_val
    ).first()

    if session_obj:
        return jsonify({
            "exists": True,
            "session_id": session_obj.id,
            "total_students": session_obj.total_students,
            "present_count": session_obj.present_count,
            "absent_count": session_obj.absent_count,
            "percentage": session_obj.percentage,
            "faculty_name": session_obj.faculty_name
        })

    return jsonify({"exists": False})


@app.route("/api/attendance/session", methods=["POST"])
@login_required
def save_attendance_session():
    if session.get("role") == "student":
        return jsonify({"success": False, "message": "Access denied. Students are not authorized to mark or modify attendance."}), 403

    data = request.json or {}

    date_str = data.get("date", "").strip()
    subject_name = data.get("subject_name", "").strip()
    section_name = data.get("section", "").strip()
    period = str(data.get("period", "1")).strip()
    topic = data.get("topic", "").strip()
    records = data.get("records", {})
    session_id = data.get("session_id")
    force_overwrite = data.get("force_overwrite", False)

    # 1. Validation
    if not date_str:
        return jsonify({"success": False, "message": "Attendance Date is required"}), 400

    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"success": False, "message": "Invalid date format. Expected YYYY-MM-DD"}), 400

    if not subject_name:
        return jsonify({"success": False, "message": "Subject is required"}), 400

    if not section_name:
        return jsonify({"success": False, "message": "Section is required"}), 400

    if not period:
        return jsonify({"success": False, "message": "Period/Session is required"}), 400

    if not records or len(records) == 0:
        return jsonify({"success": False, "message": "No student attendance records provided"}), 400

    # 2. Check for duplicate session unless session_id provided or force_overwrite is true
    existing = AttendanceSession.query.filter_by(
        date=date_str,
        subject_name=subject_name,
        section=section_name,
        period=period
    ).first()

    if existing and not session_id and not force_overwrite:
        return jsonify({
            "success": False,
            "conflict": True,
            "session_id": existing.id,
            "message": f"An attendance session already exists for {date_str}, {subject_name}, {section_name}, Period {period}."
        }), 409

    # Determine target session
    if session_id:
        target_session = db.session.get(AttendanceSession, session_id)
        if not target_session:
            return jsonify({"success": False, "message": "Session to update not found"}), 404
    elif existing:
        target_session = existing
    else:
        target_session = AttendanceSession()
        db.session.add(target_session)

    # Calculate statistics
    total_students = len(records)
    present_count = sum(1 for status in records.values() if status == "Present")
    absent_count = total_students - present_count
    percentage = round((present_count / total_students) * 100, 2) if total_students > 0 else 0.0

    target_session.date = date_str
    target_session.subject_name = subject_name
    target_session.section = section_name
    target_session.period = period
    target_session.topic = topic or "Class Lecture"
    target_session.faculty_name = data.get("faculty_name") or session.get("full_name") or "Faculty Incharge"
    target_session.faculty_id = session.get("user_id")
    target_session.total_students = total_students
    target_session.present_count = present_count
    target_session.absent_count = absent_count
    target_session.percentage = percentage
    target_session.status = "Submitted"
    target_session.updated_at = datetime.now()

    db.session.flush()

    present_students = []
    absent_students = []

    student_map = {s.roll_no: s for s in Student.query.all()}

    for roll_no, status in records.items():
        valid_status = "Present" if status == "Present" else "Absent"
        student_obj = student_map.get(roll_no)
        student_name = student_obj.name if student_obj else roll_no

        rec = AttendanceRecord.query.filter_by(
            session_id=target_session.id,
            roll_no=roll_no
        ).first()

        if rec:
            rec.status = valid_status
            rec.student_name = student_name
            rec.updated_at = datetime.now()
        else:
            rec = AttendanceRecord(
                session_id=target_session.id,
                student_id=student_obj.id if student_obj else None,
                roll_no=roll_no,
                student_name=student_name,
                status=valid_status
            )
            db.session.add(rec)

        # Legacy sync
        legacy_rec = Attendance.query.filter_by(roll_no=roll_no, date=date_str).first()
        if legacy_rec:
            legacy_rec.status = valid_status
        else:
            db.session.add(Attendance(roll_no=roll_no, date=date_str, status=valid_status))

        info = {"roll_no": roll_no, "name": student_name}
        if valid_status == "Present":
            present_students.append(info)
        else:
            absent_students.append(info)

    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Attendance saved successfully.",
        "session_id": target_session.id,
        "date": target_session.date,
        "subject": target_session.subject_name,
        "section": target_session.section,
        "period": target_session.period,
        "total_students": total_students,
        "present_count": present_count,
        "absent_count": absent_count,
        "percentage": percentage,
        "present_students": sorted(present_students, key=lambda x: x["roll_no"]),
        "absent_students": sorted(absent_students, key=lambda x: x["roll_no"])
    })


# Legacy Bulk Attendance Endpoint Support
@app.route("/api/attendance/bulk", methods=["POST"])
@login_required
def legacy_bulk_save():
    data = request.json or {}
    records = data.get("records", {})
    today = datetime.now().strftime("%Y-%m-%d")

    session_payload = {
        "date": data.get("date") or today,
        "subject_name": data.get("subject_name") or "Data Structures",
        "section": data.get("section") or "CAI-A",
        "period": data.get("period") or "1",
        "records": records,
        "force_overwrite": True
    }

    with app.test_request_context(
        "/api/attendance/session",
        method="POST",
        json=session_payload,
        headers={"Content-Type": "application/json"}
    ):
        return save_attendance_session()


@app.route("/api/attendance/session/<int:session_id>", methods=["GET"])
@login_required
def get_session_details(session_id):
    session_obj = db.session.get(AttendanceSession, session_id)
    if not session_obj:
        return jsonify({"success": False, "message": "Attendance session not found"}), 404

    records = AttendanceRecord.query.filter_by(session_id=session_id).all()
    records_map = {r.roll_no: r.status for r in records}
    
    present_list = []
    absent_list = []
    for r in records:
        item = {"roll_no": r.roll_no, "name": r.student_name, "status": r.status}
        if r.status == "Present":
            present_list.append(item)
        else:
            absent_list.append(item)

    return jsonify({
        "success": True,
        "session": {
            "id": session_obj.id,
            "date": session_obj.date,
            "subject_name": session_obj.subject_name,
            "section": session_obj.section,
            "period": session_obj.period,
            "topic": session_obj.topic,
            "faculty_name": session_obj.faculty_name,
            "total_students": session_obj.total_students,
            "present_count": session_obj.present_count,
            "absent_count": session_obj.absent_count,
            "percentage": session_obj.percentage,
            "created_at": session_obj.created_at.strftime("%Y-%m-%d %H:%M:%S") if session_obj.created_at else None,
            "updated_at": session_obj.updated_at.strftime("%Y-%m-%d %H:%M:%S") if session_obj.updated_at else None,
        },
        "records": records_map,
        "present_students": sorted(present_list, key=lambda x: x["roll_no"]),
        "absent_students": sorted(absent_list, key=lambda x: x["roll_no"])
    })


@app.route("/api/attendance/session/<int:session_id>", methods=["DELETE"])
@login_required
def delete_attendance_session(session_id):
    session_obj = db.session.get(AttendanceSession, session_id)
    if not session_obj:
        return jsonify({"success": False, "message": "Session not found"}), 404

    AttendanceRecord.query.filter_by(session_id=session_id).delete()
    db.session.delete(session_obj)
    db.session.commit()
    return jsonify({"success": True, "message": f"Attendance session for {session_obj.date} deleted successfully"})


# =============================================================================
# ATTENDANCE HISTORY APIS
# =============================================================================

@app.route("/api/attendance/history", methods=["GET"])
@login_required
def get_attendance_history():
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    subject_filter = request.args.get("subject")
    section_filter = request.args.get("section")
    period_filter = request.args.get("period")
    search = request.args.get("search", "").strip().lower()

    query = AttendanceSession.query

    if date_from:
        query = query.filter(AttendanceSession.date >= date_from)
    if date_to:
        query = query.filter(AttendanceSession.date <= date_to)
    if subject_filter:
        query = query.filter(AttendanceSession.subject_name == subject_filter)
    if section_filter:
        query = query.filter(AttendanceSession.section == section_filter)
    if period_filter:
        query = query.filter(AttendanceSession.period == period_filter)

    sessions = query.order_by(AttendanceSession.date.desc(), AttendanceSession.period.desc()).all()

    result = []
    for s in sessions:
        if search:
            match = (
                search in s.date.lower() or
                search in s.subject_name.lower() or
                search in s.section.lower() or
                search in s.faculty_name.lower() or
                (s.topic and search in s.topic.lower())
            )
            if not match:
                continue

        result.append({
            "id": s.id,
            "date": s.date,
            "subject_name": s.subject_name,
            "section": s.section,
            "period": s.period,
            "topic": s.topic,
            "faculty_name": s.faculty_name,
            "total_students": s.total_students,
            "present_count": s.present_count,
            "absent_count": s.absent_count,
            "percentage": s.percentage,
            "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else None
        })

    return jsonify(result)


# =============================================================================
# DASHBOARD & ANALYTICS APIS
# =============================================================================

@app.route("/api/dashboard", methods=["GET"])
@login_required
def dashboard_stats():
    today_str = datetime.now().strftime("%Y-%m-%d")
    threshold = get_low_attendance_threshold()

    total_enrolled = Student.query.filter_by(is_active=True).count()
    total_sessions = AttendanceSession.query.count()
    unique_dates_count = db.session.query(db.func.count(db.func.distinct(AttendanceSession.date))).scalar() or 0

    students = Student.query.filter_by(is_active=True).all()
    bulk_stats = get_all_students_day_wise_stats(students)

    # Today's day-wise stats (students attending all periods held today)
    today_sessions = AttendanceSession.query.filter_by(date=today_str).all()
    today_sessions_count = len(today_sessions)
    today_present_students = 0
    today_active_students = 0
    today_pct = 0.0

    if today_sessions_count > 0:
        today_records = AttendanceRecord.query.join(AttendanceSession).filter(
            AttendanceSession.date == today_str
        ).all()
        
        today_by_student = {}
        for r in today_records:
            if r.roll_no not in today_by_student:
                today_by_student[r.roll_no] = {"total": 0, "present": 0}
            today_by_student[r.roll_no]["total"] += 1
            if r.status == "Present":
                today_by_student[r.roll_no]["present"] += 1

        today_active_students = len(today_by_student)
        today_present_students = sum(1 for s_info in today_by_student.values() if s_info["present"] == s_info["total"] and s_info["total"] > 0)
        today_pct = round((today_present_students / today_active_students) * 100, 2) if today_active_students > 0 else 0.0

    # Overall Day-Wise rate across all enrolled students
    total_student_days = sum(s["total_days"] for s in bulk_stats.values())
    total_student_present_days = sum(s["present_days"] for s in bulk_stats.values())
    overall_percentage = round((total_student_present_days / total_student_days) * 100, 2) if total_student_days > 0 else 0.0

    low_students_list = []
    for st in students:
        st_stat = bulk_stats.get(st.roll_no)
        if not st_stat or st_stat["total_days"] == 0:
            continue
        pct = st_stat["percentage"]

        if pct < threshold:
            t_ratio = threshold / 100.0
            req = (t_ratio * st_stat["total_days"] - st_stat["present_days"]) / (1.0 - t_ratio) if t_ratio < 1.0 else 0
            shortfall = max(0, int(req) + (1 if req > int(req) else 0))

            low_students_list.append({
                "roll_no": st.roll_no,
                "name": st.name,
                "section": st.section,
                "total": st_stat["total_days"],
                "present": st_stat["present_days"],
                "absent": st_stat["absent_days"],
                "total_days": st_stat["total_days"],
                "present_days": st_stat["present_days"],
                "absent_days": st_stat["absent_days"],
                "total_classes": st_stat["total_classes"],
                "present_classes": st_stat["present_classes"],
                "absent_classes": st_stat["absent_classes"],
                "percentage": pct,
                "shortfall": shortfall
            })

    recent_sessions = AttendanceSession.query.order_by(
        AttendanceSession.date.desc(),
        AttendanceSession.period.desc()
    ).limit(5).all()

    recent_data = [{
        "id": s.id,
        "date": s.date,
        "subject_name": s.subject_name,
        "section": s.section,
        "period": s.period,
        "total": s.total_students,
        "present": s.present_count,
        "absent": s.absent_count,
        "percentage": s.percentage
    } for s in recent_sessions]

    return jsonify({
        "today_date": today_str,
        "today_sessions_count": today_sessions_count,
        "today_present_students": today_present_students,
        "today_active_students": today_active_students,
        "today_percentage": today_pct,

        "students": total_enrolled,
        "total_sessions": total_sessions,
        "total_days": unique_dates_count,
        "total_student_days": total_student_days,
        "present_student_days": total_student_present_days,
        "percentage": overall_percentage,

        "threshold": threshold,
        "low_attendance_count": len(low_students_list),
        "low_students": sorted(low_students_list, key=lambda x: x["percentage"]),
        "recent_sessions": recent_data
    })


@app.route("/api/attendance/summary")
@login_required
def attendance_summary():
    threshold = get_low_attendance_threshold()
    students = Student.query.filter_by(is_active=True).order_by(Student.roll_no).all()
    bulk_stats = get_all_students_day_wise_stats(students)

    result = []
    for student in students:
        st_stat = bulk_stats.get(student.roll_no, {
            "total_days": 0, "present_days": 0, "absent_days": 0,
            "total_classes": 0, "present_classes": 0, "absent_classes": 0,
            "percentage": 0.0
        })

        result.append({
            "roll_no": student.roll_no,
            "name": student.name,
            "section": student.section,
            "total": st_stat["total_days"],
            "present": st_stat["present_days"],
            "absent": st_stat["absent_days"],
            "total_days": st_stat["total_days"],
            "present_days": st_stat["present_days"],
            "absent_days": st_stat["absent_days"],
            "total_classes": st_stat["total_classes"],
            "present_classes": st_stat["present_classes"],
            "absent_classes": st_stat["absent_classes"],
            "percentage": st_stat["percentage"],
            "is_low": (st_stat["percentage"] < threshold and st_stat["total_days"] > 0)
        })

    return jsonify(result)


@app.route("/api/attendance/low")
@login_required
def low_attendance():
    threshold = get_low_attendance_threshold()
    students = Student.query.filter_by(is_active=True).all()
    bulk_stats = get_all_students_day_wise_stats(students)

    low_students = []
    for student in students:
        st_stat = bulk_stats.get(student.roll_no)
        if not st_stat or st_stat["total_days"] == 0:
            continue

        pct = st_stat["percentage"]
        if pct < threshold:
            t_ratio = threshold / 100.0
            required_attended = (t_ratio * st_stat["total_days"] - st_stat["present_days"]) / (1.0 - t_ratio) if t_ratio < 1.0 else 0
            shortfall = max(0, int(required_attended) + (1 if required_attended > int(required_attended) else 0))

            low_students.append({
                "roll_no": student.roll_no,
                "name": student.name,
                "section": student.section,
                "total": st_stat["total_days"],
                "present": st_stat["present_days"],
                "absent": st_stat["absent_days"],
                "total_days": st_stat["total_days"],
                "present_days": st_stat["present_days"],
                "absent_days": st_stat["absent_days"],
                "total_classes": st_stat["total_classes"],
                "present_classes": st_stat["present_classes"],
                "absent_classes": st_stat["absent_classes"],
                "percentage": pct,
                "threshold": threshold,
                "shortfall": shortfall
            })

    return jsonify(sorted(low_students, key=lambda x: x["percentage"]))


@app.route("/api/attendance/student/<roll_no>", methods=["GET"])
@login_required
def get_student_profile(roll_no):
    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    threshold = get_low_attendance_threshold()
    records = AttendanceRecord.query.filter_by(roll_no=roll_no).order_by(AttendanceRecord.created_at.desc()).all()

    total_classes = len(records)
    present_classes = sum(1 for r in records if r.status == "Present")
    absent_classes = total_classes - present_classes

    # Day-wise and subject-wise aggregation
    by_date = {}
    subject_stats = {}
    history_log = []

    for r in records:
        sess = r.session
        subj = sess.subject_name if sess else "General"
        d_str = sess.date if sess else (r.created_at.strftime("%Y-%m-%d") if r.created_at else datetime.now().strftime("%Y-%m-%d"))
        status = r.status or "Present"

        if d_str not in by_date:
            by_date[d_str] = {"total": 0, "present": 0, "absent": 0}
        by_date[d_str]["total"] += 1
        if status == "Present":
            by_date[d_str]["present"] += 1
        else:
            by_date[d_str]["absent"] += 1

        if subj not in subject_stats:
            subject_stats[subj] = {"subject": subj, "total": 0, "present": 0, "absent": 0}
        subject_stats[subj]["total"] += 1
        if status == "Present":
            subject_stats[subj]["present"] += 1
        else:
            subject_stats[subj]["absent"] += 1

        history_log.append({
            "session_id": sess.id if sess else None,
            "date": sess.date if sess else "-",
            "subject": subj,
            "period": f"Period {sess.period}" if sess else "-",
            "status": status,
            "topic": sess.topic if sess else "-",
            "faculty": sess.faculty_name if sess else "Faculty"
        })

    total_days = len(by_date)
    present_days = sum(1 for d in by_date.values() if d["present"] == d["total"] and d["total"] > 0)
    absent_days = total_days - present_days
    percentage = round((present_days / total_days) * 100, 2) if total_days > 0 else 0.0

    subject_list = []
    for s_name, s_data in subject_stats.items():
        t = s_data["total"]
        p = s_data["present"]
        p_pct = round((p / t) * 100, 1) if t > 0 else 0.0
        subject_list.append({
            "subject": s_name,
            "total": t,
            "present": p,
            "absent": s_data["absent"],
            "percentage": p_pct,
            "is_low": (p_pct < threshold and t > 0)
        })

    history_log.sort(key=lambda x: x["date"], reverse=True)

    shortfall = 0
    if percentage < threshold and total_days > 0:
        t_ratio = threshold / 100.0
        req = (t_ratio * total_days - present_days) / (1.0 - t_ratio) if t_ratio < 1.0 else 0
        shortfall = max(0, int(req) + (1 if req > int(req) else 0))

    return jsonify({
        "success": True,
        "student": {
            "roll_no": student.roll_no,
            "name": student.name,
            "department": student.department,
            "section": student.section,
            "email": student.email or "N/A",
            "is_active": student.is_active
        },
        "stats": {
            "total_days": total_days,
            "present_days": present_days,
            "absent_days": absent_days,
            "total_classes": total_classes,
            "present_classes": present_classes,
            "absent_classes": absent_classes,
            "percentage": percentage,
            "is_low": (percentage < threshold and total_days > 0),
            "threshold": threshold,
            "shortfall": shortfall
        },
        "subjects": subject_list,
        "history": history_log
    })


# =============================================================================
# STUDENT PORTAL APIS
# =============================================================================

@app.route("/api/student/dashboard", methods=["GET"])
@login_required
def get_student_dashboard():
    roll_no = request.args.get("roll_no")
    if not roll_no:
        if session.get("role") == "student":
            roll_no = session.get("roll_no")
        else:
            first_st = Student.query.filter_by(is_active=True).first()
            roll_no = first_st.roll_no if first_st else None

    if not roll_no:
        return jsonify({"success": False, "message": "Roll number not specified"}), 400

    student = Student.query.filter(db.func.upper(Student.roll_no) == roll_no.upper()).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    threshold = get_low_attendance_threshold()
    records = AttendanceRecord.query.filter_by(roll_no=student.roll_no).order_by(AttendanceRecord.created_at.desc()).all()

    total_classes = len(records)
    present_classes = sum(1 for r in records if r.status == "Present")
    absent_classes = total_classes - present_classes

    subject_stats = {}
    history_log = []
    by_date = {}
    by_month = {}

    for r in records:
        sess = r.session
        subj = sess.subject_name if sess else "General"
        d_str = sess.date if sess else datetime.now().strftime("%Y-%m-%d")
        status = r.status or "Present"

        # Subject aggregation
        if subj not in subject_stats:
            subject_stats[subj] = {"subject": subj, "total": 0, "present": 0, "absent": 0}
        subject_stats[subj]["total"] += 1
        if status == "Present":
            subject_stats[subj]["present"] += 1
        else:
            subject_stats[subj]["absent"] += 1

        # Date-wise aggregation
        if d_str not in by_date:
            try:
                dt_obj = datetime.strptime(d_str, "%Y-%m-%d")
                fmt_d = dt_obj.strftime("%a, %b %d, %Y")
                day_n = dt_obj.strftime("%A")
                m_key = dt_obj.strftime("%Y-%m")
                m_name = dt_obj.strftime("%B %Y")
            except Exception:
                fmt_d = d_str
                day_n = "-"
                m_key = d_str[:7] if len(d_str) >= 7 else "2026-09"
                m_name = m_key

            by_date[d_str] = {
                "date": d_str,
                "formatted_date": fmt_d,
                "day_name": day_n,
                "month_key": m_key,
                "month_name": m_name,
                "total": 0,
                "present": 0,
                "absent": 0,
                "percentage": 0.0,
                "status_type": "present",
                "periods": []
            }

        by_date[d_str]["total"] += 1
        if status == "Present":
            by_date[d_str]["present"] += 1
        else:
            by_date[d_str]["absent"] += 1

        # Get timing for period
        p_num = sess.period if sess else "1"
        p_times = PERIOD_TIMINGS.get(str(p_num), ("09:00 AM", "09:50 AM"))
        p_time_str = f"{p_times[0]} - {p_times[1]}"

        by_date[d_str]["periods"].append({
            "session_id": sess.id if sess else None,
            "period": str(p_num),
            "period_label": f"Period {p_num}",
            "subject": subj,
            "time": p_time_str,
            "status": status,
            "topic": sess.topic if sess else "Class Lecture",
            "faculty": sess.faculty_name if sess else "Faculty Incharge"
        })

        # Month-wise aggregation
        m_key = by_date[d_str]["month_key"]
        m_name = by_date[d_str]["month_name"]
        if m_key not in by_month:
            by_month[m_key] = {
                "month_key": m_key,
                "month_name": m_name,
                "total_classes": 0,
                "present_classes": 0,
                "absent_classes": 0,
                "total_days": 0,
                "present_days": 0,
                "absent_days": 0,
                "percentage": 0.0,
                "days_count": 0,
                "unique_dates": set(),
                "is_low": False
            }

        by_month[m_key]["total_classes"] += 1
        if status == "Present":
            by_month[m_key]["present_classes"] += 1
        else:
            by_month[m_key]["absent_classes"] += 1
        by_month[m_key]["unique_dates"].add(d_str)

        history_log.append({
            "session_id": sess.id if sess else None,
            "date": d_str,
            "period": f"Period {sess.period}" if sess else "-",
            "period_number": sess.period if sess else "1",
            "subject": subj,
            "status": status,
            "topic": sess.topic if sess else "Class Lecture",
            "faculty": sess.faculty_name if sess else "Faculty Incharge"
        })

    # Finalize by_date calculations (Full Day Only rule)
    total_days = len(by_date)
    present_days = 0

    for d_k, d_v in by_date.items():
        t = d_v["total"]
        p = d_v["present"]
        is_full_present = (p == t and t > 0)

        d_v["percentage"] = round((p / t) * 100, 1) if t > 0 else 0.0
        d_v["is_full_day_present"] = is_full_present

        if is_full_present:
            d_v["status_type"] = "present"
            present_days += 1
        elif p == 0 and t > 0:
            d_v["status_type"] = "absent"
        else:
            d_v["status_type"] = "partial"

        # Sort periods numerically
        d_v["periods"].sort(key=lambda item: int(item["period"]) if item["period"].isdigit() else 99)

    absent_days = total_days - present_days
    overall_percentage = round((present_days / total_days) * 100, 2) if total_days > 0 else 0.0

    # Finalize by_month calculations (Day-Wise per month)
    available_months = []
    for m_k, m_v in by_month.items():
        m_dates = [d_v for d_v in by_date.values() if d_v["month_key"] == m_k]
        m_tot_days = len(m_dates)
        m_pres_days = sum(1 for d in m_dates if d.get("is_full_day_present"))
        m_abs_days = m_tot_days - m_pres_days
        m_pct = round((m_pres_days / m_tot_days) * 100, 1) if m_tot_days > 0 else 0.0

        m_v["total_days"] = m_tot_days
        m_v["present_days"] = m_pres_days
        m_v["absent_days"] = m_abs_days
        m_v["percentage"] = m_pct
        m_v["days_count"] = m_tot_days
        m_v["is_low"] = (m_pct < threshold and m_tot_days > 0)
        m_v.pop("unique_dates", None)

        available_months.append({
            "key": m_k,
            "name": m_v["month_name"],
            "percentage": m_pct,
            "total": m_tot_days,
            "present": m_pres_days,
            "absent": m_abs_days,
            "total_days": m_tot_days,
            "present_days": m_pres_days,
            "absent_days": m_abs_days,
            "total_classes": m_v["total_classes"],
            "present_classes": m_v["present_classes"],
            "absent_classes": m_v["absent_classes"],
            "is_low": m_v["is_low"]
        })

    available_months.sort(key=lambda x: x["key"], reverse=True)

    subject_list = []
    for s_name, s_data in subject_stats.items():
        t = s_data["total"]
        p = s_data["present"]
        p_pct = round((p / t) * 100, 1) if t > 0 else 0.0
        subject_list.append({
            "subject": s_name,
            "total": t,
            "present": p,
            "absent": s_data["absent"],
            "percentage": p_pct,
            "is_low": (p_pct < threshold and t > 0)
        })

    # Today's day and schedule
    today_day = datetime.now().strftime("%A")
    today_periods = TimetablePeriod.query.filter_by(
        day_of_week=today_day,
        section=student.section
    ).order_by(TimetablePeriod.period_number).all()

    today_schedule = [{
        "period_number": p.period_number,
        "start_time": p.start_time,
        "end_time": p.end_time,
        "subject_name": p.subject_name,
        "subject_code": p.subject_code or "",
        "faculty_name": p.faculty_name,
        "room": p.room or "Room 301"
    } for p in today_periods]

    # Calculate shortfall in days if low
    shortfall = 0
    if overall_percentage < threshold and total_days > 0:
        t_ratio = threshold / 100.0
        req = (t_ratio * total_days - present_days) / (1.0 - t_ratio) if t_ratio < 1.0 else 0
        shortfall = max(0, int(req) + (1 if req > int(req) else 0))

    return jsonify({
        "success": True,
        "student": {
            "id": student.id,
            "roll_no": student.roll_no,
            "name": student.name,
            "department": student.department,
            "section": student.section,
            "email": student.email or f"{student.roll_no.lower()}@college.edu"
        },
        "stats": {
            "total_days": total_days,
            "present_days": present_days,
            "absent_days": absent_days,
            "total_classes": total_classes,
            "present_classes": present_classes,
            "absent_classes": absent_classes,
            "percentage": overall_percentage,
            "is_low": (overall_percentage < threshold and total_days > 0),
            "threshold": threshold,
            "shortfall": shortfall,
            "status_text": "Good Standing" if overall_percentage >= threshold else f"Attendance Warning (< {threshold}%)"
        },
        "by_date": by_date,
        "by_month": by_month,
        "available_months": available_months,
        "subjects": sorted(subject_list, key=lambda x: x["percentage"]),
        "today_day": today_day,
        "today_date": datetime.now().strftime("%Y-%m-%d"),
        "today_schedule": today_schedule,
        "history": sorted(history_log, key=lambda x: x["date"], reverse=True)
    })


@app.route("/api/student/timetable", methods=["GET"])
@login_required
def get_student_timetable():
    section_val = session.get("section") or request.args.get("section", "CAI-A")
    periods = TimetablePeriod.query.filter_by(section=section_val).all()
    day_order = {"Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4, "Friday": 5, "Saturday": 6, "Sunday": 7}
    sorted_periods = sorted(periods, key=lambda p: (day_order.get(p.day_of_week, 99), int(p.period_number) if p.period_number.isdigit() else 99))

    return jsonify({
        "success": True,
        "section": section_val,
        "periods": [{
            "id": p.id,
            "day_of_week": p.day_of_week,
            "period_number": p.period_number,
            "start_time": p.start_time,
            "end_time": p.end_time,
            "subject_name": p.subject_name,
            "subject_code": p.subject_code or "",
            "faculty_name": p.faculty_name,
            "room": p.room
        } for p in sorted_periods],
        "period_timings": PERIOD_TIMINGS
    })


@app.route("/api/student/change-password", methods=["POST"])
@login_required
def change_student_password():
    if session.get("role") != "student":
        return jsonify({"success": False, "message": "Only students can update their password via this endpoint"}), 403

    roll_no = session.get("roll_no")
    student = Student.query.filter_by(roll_no=roll_no).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    data = request.json or {}
    old_pwd = data.get("old_password", "").strip()
    new_pwd = data.get("new_password", "").strip()

    if not new_pwd or len(new_pwd) < 4:
        return jsonify({"success": False, "message": "New password must be at least 4 characters long"}), 400

    if not student.check_password(old_pwd):
        return jsonify({"success": False, "message": "Current password is incorrect"}), 400

    student.set_password(new_pwd)
    db.session.commit()
    return jsonify({"success": True, "message": "Password changed successfully"})


# =============================================================================
# EXPORT APIS (CSV, EXCEL, PDF)
# =============================================================================


@app.route("/api/export/session/<int:session_id>/<file_format>", methods=["GET"])
@login_required
def export_session_file(session_id, file_format):
    session_obj = db.session.get(AttendanceSession, session_id)
    if not session_obj:
        return jsonify({"error": "Session not found"}), 404

    college = get_college_name()
    session_data = {
        "date": session_obj.date,
        "subject_name": session_obj.subject_name,
        "section": session_obj.section,
        "period": session_obj.period,
        "topic": session_obj.topic,
        "faculty_name": session_obj.faculty_name,
        "total_students": session_obj.total_students,
        "present_count": session_obj.present_count,
        "absent_count": session_obj.absent_count,
        "percentage": session_obj.percentage
    }

    records = AttendanceRecord.query.filter_by(session_id=session_id).order_by(AttendanceRecord.roll_no).all()
    records_list = [{
        "roll_no": r.roll_no,
        "student_name": r.student_name,
        "status": r.status,
        "remarks": r.remarks
    } for r in records]

    safe_subject = session_obj.subject_name.replace(" ", "_")
    filename_base = f"Attendance_{session_obj.date}_{safe_subject}_P{session_obj.period}"

    fmt = file_format.lower()
    if fmt == "csv":
        data = export_utils.generate_session_csv(session_data, records_list, college)
        return Response(
            data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"}
        )
    elif fmt == "excel" or fmt == "xlsx":
        data = export_utils.generate_session_excel(session_data, records_list, college)
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"}
        )
    elif fmt == "pdf":
        data = export_utils.generate_session_pdf(session_data, records_list, college)
        return Response(
            data,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"}
        )
    else:
        return jsonify({"error": "Unsupported export format"}), 400


@app.route("/api/export/cumulative/<file_format>", methods=["GET"])
@login_required
def export_cumulative_file(file_format):
    threshold = get_low_attendance_threshold()
    college = get_college_name()
    only_low = request.args.get("only_low", "false").lower() == "true"
    section_filter = request.args.get("section")

    query = Student.query.filter_by(is_active=True)
    if section_filter:
        query = query.filter_by(section=section_filter)

    students = query.order_by(Student.roll_no).all()
    bulk_stats = get_all_students_day_wise_stats(students)
    summary = []

    for s in students:
        st_stat = bulk_stats.get(s.roll_no, {
            "total_days": 0, "present_days": 0, "absent_days": 0,
            "total_classes": 0, "present_classes": 0, "absent_classes": 0,
            "percentage": 0.0
        })

        pct = st_stat["percentage"]
        is_low = (pct < threshold and st_stat["total_days"] > 0)

        if only_low and not is_low:
            continue

        summary.append({
            "roll_no": s.roll_no,
            "name": s.name,
            "total": st_stat["total_days"],
            "present": st_stat["present_days"],
            "absent": st_stat["absent_days"],
            "total_days": st_stat["total_days"],
            "present_days": st_stat["present_days"],
            "absent_days": st_stat["absent_days"],
            "total_classes": st_stat["total_classes"],
            "present_classes": st_stat["present_classes"],
            "absent_classes": st_stat["absent_classes"],
            "percentage": pct,
            "is_low": is_low
        })

    filter_desc = f"Section: {section_filter or 'All'}"
    if only_low:
        filter_desc += f" | Low Attendance Only (<{threshold}%)"

    today_str = datetime.now().strftime("%Y-%m-%d")
    filename_base = f"Cumulative_Attendance_Report_{today_str}"

    fmt = file_format.lower()
    if fmt == "csv":
        data = export_utils.generate_cumulative_csv(summary, filter_desc, college)
        return Response(
            data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"}
        )
    elif fmt == "excel" or fmt == "xlsx":
        data = export_utils.generate_cumulative_excel(summary, filter_desc, threshold, college)
        return Response(
            data,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.xlsx"}
        )
    elif fmt == "pdf":
        data = export_utils.generate_cumulative_pdf(summary, filter_desc, threshold, college)
        return Response(
            data,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"}
        )
    else:
        return jsonify({"error": "Unsupported export format"}), 400


# =============================================================================
# RUN APPLICATION
# =============================================================================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
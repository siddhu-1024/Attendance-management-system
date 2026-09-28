import unittest
import json
import io
from app import app, db
from models import Student, AttendanceSession, AttendanceRecord, SystemSetting, User, Subject, Section


class TestSmartClassroomAttendanceSystem(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        with self.app.app_context():
            setting = SystemSetting.query.filter_by(key="low_attendance_threshold").first()
            if setting:
                setting.value = "75.0"
                db.session.commit()

    def login_faculty(self):
        return self.client.post("/api/login", json={
            "department": "CAI",
            "password": "CAIH@24-29"
        })

    def login_admin(self):
        return self.client.post("/api/login", json={
            "username": "admin",
            "password": "admin123"
        })

    # 1. Authentication Tests
    def test_01_authentication(self):
        # Test invalid credentials
        res = self.client.post("/api/login", json={"department": "CAI", "password": "WRONG_PASSWORD"})
        self.assertEqual(res.status_code, 401)

        # Test valid faculty login
        res = self.login_faculty()
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        # Test auth status
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200)
        auth_info = res.get_json()
        self.assertEqual(auth_info["user"]["department"], "CAI")

        # Test logout
        res = self.client.post("/api/logout")
        self.assertEqual(res.status_code, 200)

        # Test protected access after logout
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 401)

    # 2. Student & Metadata Endpoints
    def test_02_students_and_metadata(self):
        self.login_faculty()

        # Check students roster
        res = self.client.get("/api/students")
        self.assertEqual(res.status_code, 200)
        students = res.get_json()
        self.assertGreaterEqual(len(students), 41)
        self.assertIn("roll_no", students[0])
        self.assertIn("name", students[0])
        self.assertIn("attendance_percentage", students[0])

        # Check subjects
        res = self.client.get("/api/subjects")
        self.assertEqual(res.status_code, 200)
        subjects = res.get_json()
        self.assertGreaterEqual(len(subjects), 6)

        # Check sections
        res = self.client.get("/api/sections")
        self.assertEqual(res.status_code, 200)
        sections = res.get_json()
        self.assertGreaterEqual(len(sections), 4)

        # Check settings
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        settings = res.get_json()
        self.assertEqual(settings["low_attendance_threshold"], 75.0)

    # 3. Attendance Session Marking & Single Checkbox Verification
    def test_03_save_attendance_session(self):
        self.login_faculty()

        # Get active students
        res = self.client.get("/api/students?section=CAI-A")
        students = res.get_json()
        self.assertGreater(len(students), 0)

        # Mark 35 students Present (checked) and remaining Absent (unchecked)
        records = {}
        for i, st in enumerate(students):
            records[st["roll_no"]] = "Present" if i < 35 else "Absent"

        payload = {
            "date": "2026-09-28",
            "subject_name": "Data Structures",
            "section": "CAI-A",
            "period": "2",
            "topic": "Binary Search Trees & AVL Rotations",
            "records": records,
            "force_overwrite": True
        }

        res = self.client.post("/api/attendance/session", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_students"], len(students))
        self.assertEqual(data["present_count"], min(35, len(students)))
        self.assertEqual(len(data["present_students"]), min(35, len(students)))
        self.assertEqual(len(data["absent_students"]), max(0, len(students) - 35))

        expected_pct = round((min(35, len(students)) / len(students)) * 100, 2)
        self.assertEqual(data["percentage"], expected_pct)

        session_id = data["session_id"]

        # Verify duplicate detection (409 conflict when saving without force_overwrite)
        dup_payload = dict(payload)
        dup_payload["force_overwrite"] = False
        dup_payload.pop("session_id", None)
        res_dup = self.client.post("/api/attendance/session", json=dup_payload)
        self.assertEqual(res_dup.status_code, 409)

        # Verify session details endpoint
        res_details = self.client.get(f"/api/attendance/session/{session_id}")
        self.assertEqual(res_details.status_code, 200)
        details = res_details.get_json()
        self.assertEqual(details["session"]["id"], session_id)
        self.assertEqual(details["session"]["present_count"], min(35, len(students)))

    # 4. Attendance History & Filtering
    def test_04_attendance_history(self):
        self.login_faculty()

        res = self.client.get("/api/attendance/history?subject=Data Structures")
        self.assertEqual(res.status_code, 200)
        history = res.get_json()
        self.assertGreater(len(history), 0)
        self.assertEqual(history[0]["subject_name"], "Data Structures")

    # 5. Dashboard Aggregated Statistics
    def test_05_dashboard_stats(self):
        self.login_faculty()

        res = self.client.get("/api/dashboard")
        self.assertEqual(res.status_code, 200)
        stats = res.get_json()
        self.assertIn("students", stats)
        self.assertIn("total_sessions", stats)
        self.assertIn("percentage", stats)
        self.assertIn("low_students", stats)
        self.assertIn("recent_sessions", stats)
        self.assertGreater(stats["students"], 0)

    # 6. Student Attendance Profile
    def test_06_student_profile(self):
        self.login_faculty()

        # Get first student roll
        res = self.client.get("/api/students")
        first_roll = res.get_json()[0]["roll_no"]

        res = self.client.get(f"/api/attendance/student/{first_roll}")
        self.assertEqual(res.status_code, 200)
        prof = res.get_json()
        self.assertTrue(prof["success"])
        self.assertEqual(prof["student"]["roll_no"], first_roll)
        self.assertIn("stats", prof)
        self.assertIn("subjects", prof)
        self.assertIn("history", prof)

    # 7. Low Attendance Defaulters
    def test_07_low_attendance(self):
        self.login_faculty()

        res = self.client.get("/api/attendance/low")
        self.assertEqual(res.status_code, 200)
        low_list = res.get_json()
        self.assertIsInstance(low_list, list)

    # 8. Export Functionality (CSV, Excel, PDF)
    def test_08_exports(self):
        self.login_faculty()

        # Get an existing session ID
        res_hist = self.client.get("/api/attendance/history")
        sessions = res_hist.get_json()
        self.assertGreater(len(sessions), 0)
        sess_id = sessions[0]["id"]

        # Test Session CSV
        res_csv = self.client.get(f"/api/export/session/{sess_id}/csv")
        self.assertEqual(res_csv.status_code, 200)
        self.assertEqual(res_csv.mimetype, "text/csv")
        self.assertIn(b"ATTENDANCE SESSION REPORT", res_csv.data)

        # Test Session Excel (.xlsx)
        res_xlsx = self.client.get(f"/api/export/session/{sess_id}/excel")
        self.assertEqual(res_xlsx.status_code, 200)
        self.assertIn("spreadsheetml", res_xlsx.mimetype.lower())
        self.assertGreater(len(res_xlsx.data), 1000)

        # Test Session PDF
        res_pdf = self.client.get(f"/api/export/session/{sess_id}/pdf")
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.mimetype, "application/pdf")
        self.assertTrue(res_pdf.data.startswith(b"%PDF"))

        # Test Cumulative CSV
        res_cum_csv = self.client.get("/api/export/cumulative/csv")
        self.assertEqual(res_cum_csv.status_code, 200)

        # Test Cumulative Excel
        res_cum_xlsx = self.client.get("/api/export/cumulative/excel")
        self.assertEqual(res_cum_xlsx.status_code, 200)

        # Test Cumulative PDF
        res_cum_pdf = self.client.get("/api/export/cumulative/pdf")
        self.assertEqual(res_cum_pdf.status_code, 200)
        self.assertTrue(res_cum_pdf.data.startswith(b"%PDF"))

    # 9. Settings Configuration Update
    def test_09_settings_update(self):
        self.login_faculty()

        payload = {
            "low_attendance_threshold": 80.0,
            "default_attendance_state": "Present",
            "college_name": "Smart Classroom College of Technology",
            "department_name": "Department of Computer Science & AI (CAI)"
        }
        res = self.client.post("/api/settings", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        # Verify updated settings
        res_get = self.client.get("/api/settings")
        settings = res_get.get_json()
        self.assertEqual(settings["low_attendance_threshold"], 80.0)
        self.assertEqual(settings["college_name"], "Smart Classroom College of Technology")

    def login_ctpo(self):
        return self.client.post("/api/login", json={
            "username": "ctpo",
            "password": "ctpo123",
            "department": "CTPO"
        })

    def login_student(self, roll_no="256Q1A4317", password="student123"):
        return self.client.post("/api/login", json={
            "username": roll_no,
            "password": password
        })

    # 10. CTPO Login & Timetable / Period Management Tests
    def test_10_ctpo_login_and_timetable_management(self):
        # 1. Test CTPO login
        res = self.login_ctpo()
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["role"], "ctpo")

        # 2. Check Auth endpoint
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200)
        auth_data = res.get_json()
        self.assertEqual(auth_data["user"]["role"], "ctpo")

        # 3. Retrieve Timetable for Monday, Section CAI-A
        res = self.client.get("/api/timetable?day=Monday&section=CAI-A")
        self.assertEqual(res.status_code, 200)
        tt_data = res.get_json()
        self.assertTrue(tt_data["success"])
        self.assertIn("periods", tt_data)
        self.assertGreaterEqual(len(tt_data["periods"]), 1)

        # 4. Check listing of all subjects for a specific period/time
        res = self.client.get("/api/periods/for-time?period=1&section=CAI-A&date=2026-09-28")
        self.assertEqual(res.status_code, 200)
        period_time_data = res.get_json()
        self.assertTrue(period_time_data["success"])
        self.assertIn("all_subjects", period_time_data)
        self.assertGreaterEqual(len(period_time_data["all_subjects"]), 6)
        self.assertEqual(period_time_data["timing"], "09:00 AM - 09:50 AM")

        # 5. Add a new Timetable period slot
        new_period_payload = {
            "day_of_week": "Friday",
            "period_number": 8,
            "section": "CAI-A",
            "subject_name": "Deep Learning & Neural Networks",
            "subject_code": "CS403",
            "faculty_name": "Prof. S. R. Murthy",
            "room": "AI Lab 3",
            "start_time": "03:50 PM",
            "end_time": "04:40 PM"
        }
        res = self.client.post("/api/timetable", json=new_period_payload)
        self.assertEqual(res.status_code, 200)
        create_data = res.get_json()
        self.assertTrue(create_data["success"])
        new_period_id = create_data["period"]["id"]

        # 6. Edit/Update the period slot
        update_payload = {
            "subject_name": "Cloud Computing & DevOps",
            "subject_code": "CS406",
            "faculty_name": "Dr. V. K. Sharma",
            "room": "Cloud Lab 1"
        }
        res = self.client.put(f"/api/timetable/{new_period_id}", json=update_payload)
        self.assertEqual(res.status_code, 200)
        update_data = res.get_json()
        self.assertTrue(update_data["success"])
        self.assertEqual(update_data["period"]["subject_name"], "Cloud Computing & DevOps")

        # 7. Delete the period slot
        res = self.client.delete(f"/api/timetable/{new_period_id}")
        self.assertEqual(res.status_code, 200)
        del_data = res.get_json()
        self.assertTrue(del_data["success"])

    # 11. CTPO Record Attendance Session Tests
    def test_11_ctpo_record_attendance_session(self):
        self.login_ctpo()

        # Get roster
        res = self.client.get("/api/students?section=CAI-A")
        students = res.get_json()
        self.assertGreater(len(students), 0)

        # CTPO records attendance for Period 3
        records = {}
        for i, st in enumerate(students):
            records[st["roll_no"]] = "Present" if i % 2 == 0 else "Absent"

        payload = {
            "date": "2026-09-28",
            "subject_name": "Machine Learning Foundations",
            "section": "CAI-A",
            "period": "3",
            "topic": "CTPO Supervised Attendance Session - Gradient Descent Optimization",
            "records": records,
            "force_overwrite": True
        }

        res = self.client.post("/api/attendance/session", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["session_id"] > 0, True)

        # Verify CTPO session recorded in history
        res_hist = self.client.get("/api/attendance/history?period=3&subject=Machine Learning Foundations")
        self.assertEqual(res_hist.status_code, 200)
        hist = res_hist.get_json()
        self.assertGreaterEqual(len(hist), 1)

    # 12. Student Portal Login & Dashboard Tests
    def test_12_student_portal_login_and_dashboard(self):
        test_roll = "256Q1A4317"

        # 1a. Login with student roll number as BOTH username and password
        res_roll_pwd = self.client.post("/api/login", json={
            "login_type": "student",
            "studentRoll": test_roll,
            "studentPassword": test_roll
        })
        self.assertEqual(res_roll_pwd.status_code, 200)
        self.assertTrue(res_roll_pwd.get_json()["success"])

        # 1b. Login with lowercase student roll number as username and password
        res_lower = self.client.post("/api/login", json={
            "login_type": "student",
            "studentRoll": test_roll.lower(),
            "studentPassword": test_roll.lower()
        })
        self.assertEqual(res_lower.status_code, 200)
        self.assertTrue(res_lower.get_json()["success"])

        # 1c. Login with student roll number and default password
        res = self.login_student(test_roll, "student123")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["role"], "student")
        self.assertEqual(data["user"]["roll_no"], test_roll)

        # 2. Check auth status as Student
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200)
        auth = res.get_json()
        self.assertEqual(auth["user"]["role"], "student")
        self.assertTrue(auth["user"]["is_student"])

        # 3. Student Dashboard API
        res = self.client.get("/api/student/dashboard")
        self.assertEqual(res.status_code, 200)
        dash = res.get_json()
        self.assertTrue(dash["success"])
        self.assertEqual(dash["student"]["roll_no"], test_roll)
        self.assertIn("stats", dash)
        self.assertIn("percentage", dash["stats"])
        self.assertIn("total_classes", dash["stats"])
        self.assertIn("present_classes", dash["stats"])
        self.assertIn("absent_classes", dash["stats"])
        self.assertIn("subjects", dash)
        self.assertIn("today_schedule", dash)
        self.assertIn("history", dash)
        self.assertIn("by_date", dash)
        self.assertIn("by_month", dash)
        self.assertIn("available_months", dash)

        # 4. Student Timetable API
        res = self.client.get("/api/student/timetable")
        self.assertEqual(res.status_code, 200)
        tt = res.get_json()
        self.assertTrue(tt["success"])
        self.assertIn("periods", tt)
        self.assertGreaterEqual(len(tt["periods"]), 1)

        # 5. Student Change Password API
        res = self.client.post("/api/student/change-password", json={
            "old_password": "student123",
            "new_password": "newpassword123"
        })
        self.assertEqual(res.status_code, 200)
        pwd_res = res.get_json()
        self.assertTrue(pwd_res["success"])

        # Verify new password login works
        res_new_login = self.login_student(test_roll, "newpassword123")
        self.assertEqual(res_new_login.status_code, 200)

        # Revert password back to student123 for test reproducibility
        res_revert = self.client.post("/api/student/change-password", json={
            "old_password": "newpassword123",
            "new_password": "student123"
        })
        self.assertEqual(res_revert.status_code, 200)

    # 13. Student Role Security & Permission Restrictions
    def test_13_student_role_authorization_restrictions(self):
        # Login as student
        self.login_student("256Q1A4317", "student123")

        # Attempt to mark/modify attendance session -> Must be 403 Forbidden
        payload = {
            "date": "2026-09-28",
            "subject_name": "Data Structures",
            "section": "CAI-A",
            "period": "1",
            "records": {"256Q1A4317": "Present"}
        }
        res = self.client.post("/api/attendance/session", json=payload)
        self.assertEqual(res.status_code, 403)
        self.assertIn("Students are not authorized", res.get_json().get("message", ""))

        # Attempt to create timetable period slot -> Must be 403 Forbidden
        res_tt = self.client.post("/api/timetable", json={"day_of_week": "Monday", "period_number": 1})
        self.assertEqual(res_tt.status_code, 403)

        # Attempt to delete student record -> Must be 403 Forbidden
        res_del = self.client.delete("/api/students/256Q1A4317")
        self.assertEqual(res_del.status_code, 403)


if __name__ == "__main__":
    unittest.main()


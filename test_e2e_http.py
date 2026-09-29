import requests
import sys

BASE_URL = "http://127.0.0.1:5000"

def run_e2e_http_test():
    print("=== STARTING FULL E2E HTTP LIVE SERVER VALIDATION ===")
    session = requests.Session()

    # 1. Login Page Check
    print("\n1. Testing Login Page rendering (GET /)...")
    res = session.get(f"{BASE_URL}/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "Smart Classroom" in res.text, "Login page title not found"
    assert "CTPO Login" in res.text, "CTPO Login tab not found"
    assert "Student Login" in res.text, "Student Login tab not found"
    assert "Quick Access Credentials" not in res.text, "Quick Access Credentials should not be present"
    print("[PASS] Login page loads successfully with CTPO and Student login tabs.")

    # 2. Login Authentication Check
    print("\n2. Testing Faculty Login (POST /api/login)...")
    res = session.post(f"{BASE_URL}/api/login", json={
        "department": "CAI",
        "password": "CAIH@24-29"
    })
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    data = res.json()
    assert data.get("success") is True, "Login did not return success=True"
    print(f"[PASS] Login successful for user: {data['user']['full_name']} ({data['user']['role']})")

    # 3. Auth Status Check
    print("\n3. Testing Session Auth Verification (GET /api/auth/me)...")
    res = session.get(f"{BASE_URL}/api/auth/me")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    auth_data = res.json()
    assert auth_data["user"]["department"] == "CAI"
    assert auth_data["settings"]["low_attendance_threshold"] >= 0
    print(f"[PASS] Session authenticated. Threshold: {auth_data['settings']['low_attendance_threshold']}%")

    # 4. Load Students Roster Check
    print("\n4. Testing Student Roster (GET /api/students?section=CAI-A)...")
    res = session.get(f"{BASE_URL}/api/students?section=CAI-A")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    students = res.json()
    assert len(students) == 41, f"Expected 41 students, got {len(students)}"
    print(f"[PASS] Loaded {len(students)} students from database.")

    # 5. Mark Attendance & Save Check (35 Present, 6 Absent)
    print("\n5. Testing Live Attendance Saving with 35 Present and 6 Absent...")
    records = {}
    for idx, st in enumerate(students):
        records[st["roll_no"]] = "Present" if idx < 35 else "Absent"

    payload = {
        "date": "2026-09-28",
        "subject_name": "Data Structures",
        "section": "CAI-A",
        "period": "2",
        "topic": "Binary Search Trees & AVL Operations",
        "records": records,
        "force_overwrite": True
    }

    res = session.post(f"{BASE_URL}/api/attendance/session", json=payload)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    saved_data = res.json()
    assert saved_data["success"] is True
    assert saved_data["total_students"] == 41
    assert saved_data["present_count"] == 35
    assert saved_data["absent_count"] == 6
    assert saved_data["percentage"] == 85.37
    assert len(saved_data["present_students"]) == 35
    assert len(saved_data["absent_students"]) == 6
    session_id = saved_data["session_id"]
    print(f"[PASS] Attendance Session #{session_id} saved successfully.")
    print(f"       Total: {saved_data['total_students']}, Present: {saved_data['present_count']}, Absent: {saved_data['absent_count']}, Rate: {saved_data['percentage']}%")

    # 6. Duplicate Protection Check
    print("\n6. Testing Duplicate Attendance Session Protection...")
    dup_payload = dict(payload)
    dup_payload["force_overwrite"] = False
    dup_payload.pop("session_id", None)
    res_dup = session.post(f"{BASE_URL}/api/attendance/session", json=dup_payload)
    assert res_dup.status_code == 409, f"Expected 409 Conflict, got {res_dup.status_code}"
    assert res_dup.json().get("conflict") is True
    print("[PASS] Duplicate session conflict correctly intercepted and protected with 409.")

    # 7. Session Details & Student Breakdown
    print(f"\n7. Testing Session Details Retrieval (GET /api/attendance/session/{session_id})...")
    res = session.get(f"{BASE_URL}/api/attendance/session/{session_id}")
    assert res.status_code == 200
    details = res.json()
    assert details["session"]["present_count"] == 35
    assert details["session"]["absent_count"] == 6
    print(f"[PASS] Session details verified with {len(details['present_students'])} present and {len(details['absent_students'])} absent items.")

    # 8. Dashboard Live Metrics Check
    print("\n8. Testing Live Dashboard Stats (GET /api/dashboard)...")
    res = session.get(f"{BASE_URL}/api/dashboard")
    assert res.status_code == 200
    dash_stats = res.json()
    assert dash_stats["students"] == 41
    assert dash_stats["total_sessions"] >= 1
    print(f"[PASS] Dashboard live stats: Total Students={dash_stats['students']}, Total Sessions={dash_stats['total_sessions']}, Overall Rate={dash_stats['percentage']}%")

    # 9. Attendance History Check
    print("\n9. Testing Attendance History (GET /api/attendance/history)...")
    res = session.get(f"{BASE_URL}/api/attendance/history")
    assert res.status_code == 200
    history = res.json()
    assert len(history) >= 1
    print(f"[PASS] History contains {len(history)} sessions logged.")

    # 10. Individual Student Profile Analytics Check
    sample_roll = students[0]["roll_no"]
    print(f"\n10. Testing Student Profile Analytics (GET /api/attendance/student/{sample_roll})...")
    res = session.get(f"{BASE_URL}/api/attendance/student/{sample_roll}")
    assert res.status_code == 200
    prof = res.json()
    assert prof["success"] is True
    assert prof["student"]["roll_no"] == sample_roll
    print(f"[PASS] Student profile for {prof['student']['name']} loaded: Attended {prof['stats']['present_days']}/{prof['stats']['total_days']} days ({prof['stats']['percentage']}%)")

    # 11. Low Attendance Defaulters Check
    print("\n11. Testing Low Attendance Defaulter List (GET /api/attendance/low)...")
    res = session.get(f"{BASE_URL}/api/attendance/low")
    assert res.status_code == 200
    low_data = res.json()
    print(f"[PASS] Low attendance list returned {len(low_data)} defaulters.")

    # 12. Real Export Validation (CSV, Excel, PDF)
    print("\n12. Testing Real Exports on live server...")
    
    # Session CSV
    res = session.get(f"{BASE_URL}/api/export/session/{session_id}/csv")
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("Content-Type")
    assert len(res.content) > 100
    print(f"[PASS] Session CSV export verified ({len(res.content)} bytes)")

    # Session Excel (.xlsx)
    res = session.get(f"{BASE_URL}/api/export/session/{session_id}/excel")
    assert res.status_code == 200
    assert len(res.content) > 1000
    print(f"[PASS] Session Excel (.xlsx) export verified ({len(res.content)} bytes)")

    # Session PDF
    res = session.get(f"{BASE_URL}/api/export/session/{session_id}/pdf")
    assert res.status_code == 200
    assert res.content.startswith(b"%PDF")
    print(f"[PASS] Session PDF export verified ({len(res.content)} bytes)")

    # 13. CTPO Login & Timetable Management Validation
    print("\n13. Testing CTPO Login & Period Timetable Management...")
    ctpo_session = requests.Session()
    res = ctpo_session.post(f"{BASE_URL}/api/login", json={
        "username": "ctpo",
        "password": "ctpo123",
        "department": "CTPO"
    })
    assert res.status_code == 200, f"CTPO login failed: {res.status_code}"
    ctpo_data = res.json()
    assert ctpo_data["user"]["role"] == "ctpo"
    print(f"[PASS] CTPO logged in successfully: {ctpo_data['user']['full_name']} ({ctpo_data['user']['role']})")

    # Timetable Fetch
    res = ctpo_session.get(f"{BASE_URL}/api/timetable?day=Monday&section=CAI-A")
    assert res.status_code == 200
    tt_data = res.json()
    assert tt_data["success"] is True
    assert len(tt_data["periods"]) >= 1
    print(f"[PASS] CTPO fetched {len(tt_data['periods'])} timetable period slots for Monday (CAI-A).")

    # List All Subjects For Time Slot
    res = ctpo_session.get(f"{BASE_URL}/api/periods/for-time?period=1&section=CAI-A&date=2026-09-28")
    assert res.status_code == 200
    p_time_data = res.json()
    assert p_time_data["success"] is True
    assert len(p_time_data["all_subjects"]) >= 6
    print(f"[PASS] CTPO retrieved subject list for Period 1 ({p_time_data['timing']}): Scheduled: {p_time_data['scheduled_subject']}, Total available subjects: {len(p_time_data['all_subjects'])}")

    # Add Period Slot
    res = ctpo_session.post(f"{BASE_URL}/api/timetable", json={
        "day_of_week": "Saturday",
        "period_number": 6,
        "section": "CAI-A",
        "subject_name": "Artificial Intelligence & Expert Systems",
        "subject_code": "CS401",
        "faculty_name": "Dr. K. Srinivas",
        "room": "AI Research Lab 1",
        "start_time": "02:10 PM",
        "end_time": "03:00 PM"
    })
    assert res.status_code == 200
    created_slot = res.json()
    assert created_slot["success"] is True
    new_slot_id = created_slot["period"]["id"]
    print(f"[PASS] CTPO successfully created new period slot #{new_slot_id} on Saturday.")

    # Edit Period Slot
    res = ctpo_session.put(f"{BASE_URL}/api/timetable/{new_slot_id}", json={
        "subject_name": "Cloud Computing & DevOps",
        "room": "Cloud Lab 2"
    })
    assert res.status_code == 200
    updated_slot = res.json()
    assert updated_slot["success"] is True
    assert updated_slot["period"]["subject_name"] == "Cloud Computing & DevOps"
    print(f"[PASS] CTPO updated period slot #{new_slot_id} to '{updated_slot['period']['subject_name']}'.")

    # Delete Period Slot
    res = ctpo_session.delete(f"{BASE_URL}/api/timetable/{new_slot_id}")
    assert res.status_code == 200
    print(f"[PASS] CTPO cleaned up/deleted test period slot #{new_slot_id}.")

    # 14. CTPO Recording Attendance Session
    print("\n14. Testing CTPO Period Attendance Recording...")
    ctpo_records = {}
    for idx, st in enumerate(students):
        ctpo_records[st["roll_no"]] = "Present" if idx % 2 == 0 else "Absent"

    ctpo_att_payload = {
        "date": "2026-09-28",
        "subject_name": "Web Technologies & Full Stack",
        "section": "CAI-A",
        "period": "4",
        "topic": "CTPO Attendance Record - REST APIs & State Management",
        "records": ctpo_records,
        "force_overwrite": True
    }
    res = ctpo_session.post(f"{BASE_URL}/api/attendance/session", json=ctpo_att_payload)
    assert res.status_code == 200
    ctpo_att_res = res.json()
    assert ctpo_att_res["success"] is True
    print(f"[PASS] CTPO saved Attendance Session #{ctpo_att_res['session_id']} for Period 4 ({ctpo_att_res['subject']}).")

    # 15. Student Portal Login & Dashboard Analytics
    print("\n15. Testing Student Portal Login & Student Dashboard...")
    student_session = requests.Session()
    target_student_roll = "256Q1A4317"
    res = student_session.post(f"{BASE_URL}/api/login", json={
        "login_type": "student",
        "studentRoll": target_student_roll,
        "studentPassword": target_student_roll
    })
    assert res.status_code == 200, f"Student login failed: {res.status_code}"
    stu_login_data = res.json()
    assert stu_login_data["user"]["role"] == "student"
    assert stu_login_data["user"]["roll_no"] == target_student_roll
    print(f"[PASS] Student logged in: {stu_login_data['user']['full_name']} (Roll: {stu_login_data['user']['roll_no']})")

    # Student Dashboard Check
    res = student_session.get(f"{BASE_URL}/api/student/dashboard")
    assert res.status_code == 200
    stu_dash = res.json()
    assert stu_dash["success"] is True
    assert stu_dash["student"]["roll_no"] == target_student_roll
    assert "stats" in stu_dash
    assert "subjects" in stu_dash
    assert "today_schedule" in stu_dash
    assert "history" in stu_dash
    print(f"[PASS] Student Dashboard verified: Attendance Rate={stu_dash['stats']['percentage']}%, Attended={stu_dash['stats']['present_days']}/{stu_dash['stats']['total_days']} days, Total Subjects={len(stu_dash['subjects'])}")

    # Student Weekly Timetable Check
    res = student_session.get(f"{BASE_URL}/api/student/timetable")
    assert res.status_code == 200
    stu_tt = res.json()
    assert stu_tt["success"] is True
    assert len(stu_tt["periods"]) >= 1
    print(f"[PASS] Student Timetable retrieved {len(stu_tt['periods'])} periods across weekly schedule.")

    # 16. Student Password Update Validation
    print("\n16. Testing Student Password Change & Re-Authentication...")
    res = student_session.post(f"{BASE_URL}/api/student/change-password", json={
        "old_password": "student123",
        "new_password": "testpwd_updated_456"
    })
    assert res.status_code == 200
    assert res.json()["success"] is True
    print("[PASS] Student password successfully changed.")

    # Validate login with updated password
    check_sess = requests.Session()
    res = check_sess.post(f"{BASE_URL}/api/login", json={
        "username": target_student_roll,
        "password": "testpwd_updated_456"
    })
    assert res.status_code == 200
    print("[PASS] Re-login with new student password succeeded.")

    # Revert password back to student123
    res = check_sess.post(f"{BASE_URL}/api/student/change-password", json={
        "old_password": "testpwd_updated_456",
        "new_password": "student123"
    })
    assert res.status_code == 200
    print("[PASS] Student password reverted back to standard default.")

    # 17. Security Check: Student Blocked from Modifying Attendance
    print("\n17. Testing Security Protection: Students Blocked from Attendance Modification...")
    bad_attempt = student_session.post(f"{BASE_URL}/api/attendance/session", json={
        "date": "2026-09-28",
        "subject_name": "Data Structures",
        "section": "CAI-A",
        "period": "1",
        "records": {target_student_roll: "Present"}
    })
    assert bad_attempt.status_code == 403, f"Expected 403 Forbidden, got {bad_attempt.status_code}"
    print("[PASS] Student attendance marking attempt correctly rejected with 403 Forbidden.")

    print("\n=======================================================")
    print("ALL 17 E2E HTTP LIVE SERVER VALIDATION CHECKS PASSED!")
    print("=======================================================\n")

if __name__ == "__main__":
    run_e2e_http_test()


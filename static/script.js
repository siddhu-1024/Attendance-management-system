/**
 * SMART CLASSROOM ATTENDANCE & PERIOD MANAGEMENT SYSTEM
 * Production Frontend Application Controller (CTPO & Student Portals)
 */

// =============================================================================
// GLOBAL APPLICATION STATE
// =============================================================================

let currentUser = null;
let systemSettings = {
    low_attendance_threshold: 75.0,
    default_attendance_state: "Present",
    college_name: "Smart Classroom Institute of Technology",
    department_name: "Department of Computer Science & AI (CAI)"
};

let allStudents = [];
let subjectsList = [];
let sectionsList = [];

// Session Attendance State
let attendanceMap = {}; // { [roll_no]: "Present" | "Absent" }
let currentEditingSessionId = null;
let activeRosterFilter = 'all'; // 'all' | 'present' | 'absent'
let lastSavedSession = null;
let confirmActionCallback = null;

// Timetable & CTPO State
let selectedTimetableDay = "Monday";
let allTimetablePeriods = [];
let currentScheduledSubject = null;

// Student Portal State
let currentStudentData = null;
let studentTimetableData = [];


// =============================================================================
// APP INITIALIZATION
// =============================================================================

document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    try {
        startLiveClock();
        setTodayDate();

        // 1. Load User Session and System Settings
        const authRes = await fetch("/api/auth/me");
        if (authRes.status === 401) {
            window.location.href = "/";
            return;
        }
        const authData = await authRes.json();
        currentUser = authData.user;
        if (authData.settings) {
            systemSettings = Object.assign(systemSettings, authData.settings);
        }

        renderUserHeader();

        // 2. Branch between Student Mode and Staff / CTPO / Admin Mode
        if (currentUser.is_student || currentUser.role === "student") {
            initStudentView();
        } else {
            initStaffAndCtpoView();
        }

    } catch (error) {
        console.error("Initialization error:", error);
        showToast("Error connecting to server. Please refresh.", "error");
    }
}

function startLiveClock() {
    const clockEl = document.getElementById("currentDateDisplay");
    const update = () => {
        const now = new Date();
        const options = { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' };
        clockEl.textContent = now.toLocaleDateString('en-US', options);
    };
    update();
    setInterval(update, 30000);
}

function setTodayDate() {
    const today = new Date().toISOString().split('T')[0];
    const dateInput = document.getElementById("sessionDate");
    if (dateInput) {
        dateInput.value = today;
    }
}

function renderUserHeader() {
    if (!currentUser) return;
    const nameEl = document.getElementById("userNameDisplay");
    const roleEl = document.getElementById("userRoleDisplay");
    const avatarEl = document.getElementById("userAvatar");

    nameEl.textContent = currentUser.full_name || currentUser.username;
    
    if (currentUser.role === "student") {
        roleEl.textContent = `Student • ${currentUser.roll_no} (${currentUser.section})`;
        avatarEl.textContent = (currentUser.roll_no || "STU").substring(0, 3).toUpperCase();
    } else if (currentUser.role === "ctpo") {
        roleEl.textContent = `CTPO • Timetable & Period In-Charge`;
        avatarEl.textContent = "CTPO";
    } else if (currentUser.role === "admin") {
        roleEl.textContent = `Admin • Department Head`;
        avatarEl.textContent = "ADM";
    } else {
        roleEl.textContent = `Faculty • ${currentUser.department}`;
        avatarEl.textContent = (currentUser.full_name || currentUser.username).substring(0, 3).toUpperCase();
    }

    if (systemSettings.college_name) {
        document.getElementById("headerCollegeName").textContent = systemSettings.college_name;
    }
    if (systemSettings.department_name) {
        document.getElementById("headerDeptName").textContent = systemSettings.department_name;
    }
}


// =============================================================================
// VIEW INITIALIZERS (STAFF/CTPO VS STUDENT)
// =============================================================================

async function initStaffAndCtpoView() {
    // Show staff nav tabs, hide student tabs
    document.querySelectorAll(".staff-only").forEach(el => el.classList.remove("hidden"));
    document.querySelectorAll(".student-only").forEach(el => el.classList.add("hidden"));

    // CTPO specific badge rendering
    const ctpoBadge = document.getElementById("navCtpoBadge");
    if (currentUser.role === "ctpo") {
        ctpoBadge.textContent = "ACTIVE";
        ctpoBadge.className = "badge-pill success";
    }

    // Load Selectors & Metadata in parallel
    await Promise.all([
        loadSubjects(),
        loadSections(),
        loadStudentsRoster()
    ]);

    // Load Timetable & Background Data
    loadTimetable();
    loadDashboardStats();
    loadAttendanceHistory();
    loadLowAttendanceData();
    loadAdminRoster();
    loadSettingsForm();

    // Default to Mark Attendance Tab
    switchTab("mark-attendance");
}

async function initStudentView() {
    // Hide staff nav tabs, show student nav tabs
    document.querySelectorAll(".staff-only").forEach(el => el.classList.add("hidden"));
    document.querySelectorAll(".student-only").forEach(el => el.classList.remove("hidden"));

    // Load Student Dashboard and Timetable
    await Promise.all([
        loadStudentDashboard(),
        loadStudentTimetable()
    ]);

    // Switch to Student Dashboard Tab
    switchTab("student-dashboard");
}


// =============================================================================
// NAVIGATION & TAB SWITCHING
// =============================================================================

function switchTab(tabId) {
    document.querySelectorAll(".nav-tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.tab === tabId);
    });

    document.querySelectorAll(".tab-pane").forEach(pane => {
        pane.classList.remove("active");
    });

    const targetPane = document.getElementById(`tab-${tabId}`);
    if (targetPane) {
        targetPane.classList.add("active");
    }

    // Refresh tab-specific data on activation
    if (tabId === "periods-timetable") {
        loadTimetable();
    } else if (tabId === "mark-attendance") {
        updateCtpoPeriodLink();
    } else if (tabId === "dashboard-overview") {
        loadDashboardStats();
    } else if (tabId === "attendance-history") {
        loadAttendanceHistory();
    } else if (tabId === "low-attendance") {
        loadLowAttendanceData();
    } else if (tabId === "student-profile") {
        populateStudentProfileDropdown();
    } else if (tabId === "export-reports") {
        populateExportSessionDropdown();
    } else if (tabId === "roster-management") {
        loadAdminRoster();
    } else if (tabId === "system-settings") {
        loadSettingsForm();
    } else if (tabId === "student-dashboard") {
        loadStudentDashboard();
    } else if (tabId === "student-schedule") {
        loadStudentTimetable();
    }
}

async function handleLogout() {
    showConfirm("Sign Out", "Are you sure you want to sign out of the system?", async () => {
        try {
            await fetch("/api/logout", { method: "POST" });
            window.location.href = "/";
        } catch (e) {
            window.location.href = "/";
        }
    });
}


// =============================================================================
// METADATA & SELECTORS LOADER
// =============================================================================

async function loadSubjects() {
    try {
        const res = await fetch("/api/subjects");
        subjectsList = await res.json();
        
        const sessionSelect = document.getElementById("sessionSubject");
        const histSelect = document.getElementById("histSubject");
        const editPeriodSubject = document.getElementById("editPeriodSubject");

        let optionsHtml = subjectsList.map(s => `<option value="${s.name}">${s.name} (${s.code})</option>`).join("");
        
        if (sessionSelect) sessionSelect.innerHTML = optionsHtml;
        if (histSelect) histSelect.innerHTML = `<option value="">All Subjects</option>` + optionsHtml;
        if (editPeriodSubject) editPeriodSubject.innerHTML = optionsHtml;

    } catch (e) {
        console.error("Error loading subjects:", e);
    }
}

async function loadSections() {
    try {
        const res = await fetch("/api/sections");
        sectionsList = await res.json();

        const sessionSec = document.getElementById("sessionSection");
        const histSec = document.getElementById("histSection");
        const expSec = document.getElementById("exportCumSection");
        const ttSec = document.getElementById("timetableSectionSelect");

        let optionsHtml = sectionsList.map(s => `<option value="${s.name}">${s.name}</option>`).join("");
        
        if (sessionSec) sessionSec.innerHTML = optionsHtml;
        if (histSec) histSec.innerHTML = `<option value="">All Sections</option>` + optionsHtml;
        if (expSec) expSec.innerHTML = `<option value="">All Sections</option>` + optionsHtml;
        if (ttSec) ttSec.innerHTML = optionsHtml;

    } catch (e) {
        console.error("Error loading sections:", e);
    }
}


// =============================================================================
// CTPO PERIOD & TIMETABLE MANAGEMENT
// =============================================================================

function selectTimetableDay(day) {
    selectedTimetableDay = day;
    document.querySelectorAll("#timetableDayTabs .day-tab-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.day === day);
    });
    const titleDisplay = document.getElementById("currentDayTitleDisplay");
    if (titleDisplay) titleDisplay.textContent = day;
    loadTimetable();
}

async function loadTimetable() {
    try {
        const secSelect = document.getElementById("timetableSectionSelect");
        const section = secSelect ? secSelect.value : "CAI-A";
        const day = selectedTimetableDay || "Monday";

        const res = await fetch(`/api/timetable?day=${encodeURIComponent(day)}&section=${encodeURIComponent(section)}`);
        const data = await res.json();

        if (data.success) {
            allTimetablePeriods = data.periods;
            renderTimetableGrid(data.periods, data.period_timings);
            renderDaySubjectsTable(data.periods);
        }
    } catch (e) {
        console.error("Error loading timetable:", e);
    }
}

function renderTimetableGrid(periods, periodTimings = {}) {
    const grid = document.getElementById("periodCardsGrid");
    if (!grid) return;

    if (!periods || periods.length === 0) {
        grid.innerHTML = `
            <div class="card p-4 text-center text-muted span-full" style="grid-column: 1 / -1;">
                <p>No period timetable entries found for ${selectedTimetableDay}.</p>
                <button class="btn btn-primary btn-sm mt-3" onclick="openAddPeriodModal()">+ Add Period 1 for ${selectedTimetableDay}</button>
            </div>
        `;
        return;
    }

    grid.innerHTML = periods.map(p => `
        <div class="period-card" id="period-card-${p.id}">
            <div class="period-card-top">
                <span class="period-number-badge">Period ${p.period_number}</span>
                <span class="period-time-badge">${p.start_time} - ${p.end_time}</span>
            </div>
            <div class="period-subject-title">${p.subject_name}</div>
            <div class="period-meta-line">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
                <span>${p.faculty_name}</span>
            </div>
            <div class="period-meta-line">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                </svg>
                <span>${p.room || 'Room 301'} • ${p.section}</span>
            </div>
            <div class="period-actions">
                <button class="btn btn-primary btn-sm" onclick="startAttendanceForPeriod('${p.period_number}', '${escapeHtml(p.subject_name)}', '${p.section}')" title="Record Attendance">
                    <span>Take Attendance</span>
                </button>
                <button class="btn btn-outline-secondary btn-sm" onclick="openEditPeriodModal(${p.id})" title="Edit Period">
                    <span>Edit</span>
                </button>
                <button class="btn btn-outline-danger btn-sm" onclick="deletePeriodSlot(${p.id}, '${p.period_number}', '${p.day_of_week}')" title="Delete">
                    <span>✕</span>
                </button>
            </div>
        </div>
    `).join("");
}

function renderDaySubjectsTable(periods) {
    const tbody = document.getElementById("daySubjectsTableBody");
    if (!tbody) return;

    if (!periods || periods.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center py-3 text-muted">No classes scheduled for this day.</td></tr>`;
        return;
    }

    tbody.innerHTML = periods.map(p => `
        <tr>
            <td class="font-bold">Period ${p.period_number}</td>
            <td class="font-mono text-xs">${p.start_time} - ${p.end_time}</td>
            <td class="font-semibold text-primary">${p.subject_name}</td>
            <td><span class="mono-badge">${p.subject_code || '-'}</span></td>
            <td>${p.faculty_name}</td>
            <td>${p.room || 'Room 301'}</td>
            <td style="text-align: center;">
                <button class="btn btn-xs btn-primary" onclick="startAttendanceForPeriod('${p.period_number}', '${escapeHtml(p.subject_name)}', '${p.section}')">
                    <span>Mark Attendance</span>
                </button>
            </td>
        </tr>
    `).join("");
}

function startAttendanceForPeriod(periodNum, subjectName, section) {
    switchTab("mark-attendance");

    const pSelect = document.getElementById("sessionPeriod");
    const sSelect = document.getElementById("sessionSubject");
    const secSelect = document.getElementById("sessionSection");

    if (pSelect) pSelect.value = periodNum;
    if (secSelect) secSelect.value = section;
    if (sSelect) {
        // Find subject in dropdown or add temporarily
        let found = false;
        for (let opt of sSelect.options) {
            if (opt.value === subjectName) {
                opt.selected = true;
                found = true;
                break;
            }
        }
        if (!found) {
            const newOpt = document.createElement("option");
            newOpt.value = subjectName;
            newOpt.textContent = subjectName;
            newOpt.selected = true;
            sSelect.appendChild(newOpt);
        }
    }

    loadStudentsRoster();
    updateCtpoPeriodLink();
    showToast(`Loaded Period ${periodNum} (${subjectName}) into attendance marker.`, "info");
}

async function onPeriodChange() {
    await updateCtpoPeriodLink();
    onSessionConfigChange();
}

async function updateCtpoPeriodLink() {
    const period = document.getElementById("sessionPeriod") ? document.getElementById("sessionPeriod").value : "1";
    const section = document.getElementById("sessionSection") ? document.getElementById("sessionSection").value : "CAI-A";
    const date = document.getElementById("sessionDate") ? document.getElementById("sessionDate").value : "";

    try {
        const res = await fetch(`/api/periods/for-time?period=${period}&section=${encodeURIComponent(section)}&date=${date}`);
        const data = await res.json();

        if (data.success) {
            const helperInfo = document.getElementById("ctpoHelperScheduledInfo");
            if (helperInfo) {
                if (data.scheduled_subject) {
                    helperInfo.innerHTML = `${data.day} • Period ${period} (${data.timing}) • Scheduled: <strong>${data.scheduled_subject}</strong> (${data.scheduled_faculty})`;
                    // Auto select the subject if in new session mode
                    if (!currentEditingSessionId) {
                        const sSelect = document.getElementById("sessionSubject");
                        if (sSelect) {
                            for (let opt of sSelect.options) {
                                if (opt.value === data.scheduled_subject) {
                                    opt.selected = true;
                                    break;
                                }
                            }
                        }
                    }
                } else {
                    helperInfo.innerHTML = `${data.day} • Period ${period} (${data.timing}) • <em>No specific subject mapped in CTPO timetable</em>`;
                }
            }
        }
    } catch (e) {
        console.error("Error updating period link:", e);
    }
}

async function loadSubjectsForCurrentPeriodTime() {
    const period = document.getElementById("sessionPeriod").value;
    const date = document.getElementById("sessionDate").value;
    const section = document.getElementById("sessionSection").value;

    try {
        const res = await fetch(`/api/periods/for-time?period=${period}&section=${encodeURIComponent(section)}&date=${date}`);
        const data = await res.json();

        if (data.success && data.all_subjects) {
            const subjectNames = data.all_subjects.map(s => `• ${s.name} (${s.code})`).join("\n");
            showToast(`Subjects available for Period ${period} (${data.timing}):\n${subjectNames}`, "info");
        }
    } catch (e) {
        showToast("Error retrieving subjects.", "error");
    }
}

function openAddPeriodModal() {
    document.getElementById("editPeriodId").value = "";
    document.getElementById("editPeriodModalTitle").textContent = "Add New Period Slot";
    document.getElementById("editPeriodDay").value = selectedTimetableDay || "Monday";
    document.getElementById("editPeriodNumber").value = "1";
    document.getElementById("editPeriodFaculty").value = "Faculty Incharge";
    document.getElementById("editPeriodRoom").value = "Room 301";
    document.getElementById("editPeriodStartTime").value = "09:00 AM";
    document.getElementById("editPeriodEndTime").value = "09:50 AM";
    document.getElementById("editPeriodModal").classList.remove("hidden");
}

function openEditPeriodModal(periodId) {
    const periodObj = allTimetablePeriods.find(p => p.id === periodId);
    if (!periodObj) return;

    document.getElementById("editPeriodId").value = periodObj.id;
    document.getElementById("editPeriodModalTitle").textContent = `Edit Period ${periodObj.period_number} (${periodObj.day_of_week})`;
    document.getElementById("editPeriodDay").value = periodObj.day_of_week;
    document.getElementById("editPeriodNumber").value = periodObj.period_number;
    document.getElementById("editPeriodSection").value = periodObj.section;
    document.getElementById("editPeriodSubject").value = periodObj.subject_name;
    document.getElementById("editPeriodFaculty").value = periodObj.faculty_name;
    document.getElementById("editPeriodRoom").value = periodObj.room || "Room 301";
    document.getElementById("editPeriodStartTime").value = periodObj.start_time;
    document.getElementById("editPeriodEndTime").value = periodObj.end_time;
    document.getElementById("editPeriodModal").classList.remove("hidden");
}

function closeEditPeriodModal() {
    document.getElementById("editPeriodModal").classList.add("hidden");
}

function onEditPeriodNumberChange() {
    const pNum = document.getElementById("editPeriodNumber").value;
    const timings = {
        "1": ["09:00 AM", "09:50 AM"],
        "2": ["09:50 AM", "10:40 AM"],
        "3": ["10:50 AM", "11:40 AM"],
        "4": ["11:40 AM", "12:30 PM"],
        "5": ["01:20 PM", "02:10 PM"],
        "6": ["02:10 PM", "03:00 PM"],
        "7": ["03:00 PM", "03:50 PM"],
        "8": ["03:50 PM", "04:40 PM"],
    };
    if (timings[pNum]) {
        document.getElementById("editPeriodStartTime").value = timings[pNum][0];
        document.getElementById("editPeriodEndTime").value = timings[pNum][1];
    }
}

async function handleSavePeriod(e) {
    e.preventDefault();
    const periodId = document.getElementById("editPeriodId").value;
    const day = document.getElementById("editPeriodDay").value;
    const periodNum = document.getElementById("editPeriodNumber").value;
    const section = document.getElementById("editPeriodSection").value;
    const subjectName = document.getElementById("editPeriodSubject").value;
    const faculty = document.getElementById("editPeriodFaculty").value;
    const room = document.getElementById("editPeriodRoom").value;
    const startTime = document.getElementById("editPeriodStartTime").value;
    const endTime = document.getElementById("editPeriodEndTime").value;

    const subjectObj = subjectsList.find(s => s.name === subjectName);
    const subjectCode = subjectObj ? subjectObj.code : "";

    const payload = {
        day_of_week: day,
        period_number: periodNum,
        section: section,
        subject_name: subjectName,
        subject_code: subjectCode,
        faculty_name: faculty,
        room: room,
        start_time: startTime,
        end_time: endTime
    };

    try {
        let res;
        if (periodId) {
            res = await fetch(`/api/timetable/${periodId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        } else {
            res = await fetch("/api/timetable", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        }

        const data = await res.json();
        if (data.success) {
            showToast("Period schedule saved successfully.", "success");
            closeEditPeriodModal();
            loadTimetable();
        } else {
            showToast(data.message || "Failed to save period schedule.", "error");
        }
    } catch (err) {
        showToast("Error saving period slot.", "error");
    }
}

function deletePeriodSlot(periodId, periodNum, day) {
    showConfirm("Delete Period", `Are you sure you want to delete Period ${periodNum} (${day}) from the timetable?`, async () => {
        try {
            const res = await fetch(`/api/timetable/${periodId}`, { method: "DELETE" });
            const data = await res.json();
            if (data.success) {
                showToast("Period slot deleted.", "success");
                loadTimetable();
            } else {
                showToast(data.message || "Failed to delete.", "error");
            }
        } catch (e) {
            showToast("Server error deleting period slot.", "error");
        }
    });
}


// =============================================================================
// STUDENT PORTAL LOGIC & DASHBOARD
// Student Portal State
let studentAttendanceMode = "overall";
let studentCalYear = new Date().getFullYear();
let studentCalMonth = new Date().getMonth(); // 0-11
let studentSelectedDate = null;
let studentSelectedMonthKey = null;

async function loadStudentDashboard() {
    try {
        const res = await fetch("/api/student/dashboard");
        const data = await res.json();

        if (data.success) {
            currentStudentData = data;
            
            // Set default selected month & date from data if available
            if (data.available_months && data.available_months.length > 0) {
                studentSelectedMonthKey = data.available_months[0].key;
                const [y, m] = studentSelectedMonthKey.split("-");
                studentCalYear = parseInt(y, 10);
                studentCalMonth = parseInt(m, 10) - 1;
            }

            if (data.by_date) {
                const dates = Object.keys(data.by_date).sort();
                if (dates.length > 0) {
                    studentSelectedDate = dates[dates.length - 1]; // latest date
                }
            }
            if (!studentSelectedDate) {
                studentSelectedDate = new Date().toISOString().split("T")[0];
            }

            renderStudentDashboard(data);
        } else {
            showToast(data.message || "Unable to load student attendance record.", "error");
        }
    } catch (e) {
        console.error("Error loading student dashboard:", e);
    }
}

function renderStudentDashboard(data) {
    const student = data.student;
    const stats = data.stats;

    // Header Hero Info
    document.getElementById("studentHeroName").textContent = student.name;
    document.getElementById("studentHeroRoll").textContent = student.roll_no;
    document.getElementById("studentHeroDept").textContent = `${student.department} • Section ${student.section}`;
    document.getElementById("studentHeroAvatar").textContent = student.name.substring(0, 2).toUpperCase();

    const statusBadge = document.getElementById("studentHeroStatusBadge");
    if (stats.is_low) {
        statusBadge.className = "hero-pill status danger";
        statusBadge.textContent = `⚠️ Low Attendance Alert (< ${stats.threshold}%)`;
    } else {
        statusBadge.className = "hero-pill status";
        statusBadge.textContent = `✓ Attendance Safe (≥ ${stats.threshold}%)`;
    }

    // Populate Month Selector dropdown
    const monthSelect = document.getElementById("studentMonthSelect");
    if (monthSelect && data.available_months) {
        monthSelect.innerHTML = data.available_months.map(m => `
            <option value="${m.key}" ${m.key === studentSelectedMonthKey ? 'selected' : ''}>
                ${m.name} (${m.percentage}% - ${m.present}/${m.total})
            </option>
        `).join("");
    }

    // Update KPI Display for Current View Mode
    updateStudentKpiDisplay();

    // Render Calendar & Day Inspector
    renderStudentCalendar();
    if (studentSelectedDate) {
        selectStudentCalendarDate(studentSelectedDate);
    }

    // Render Next % Calculator
    calculateNextPercentage();
    calculateTargetGoal();

    // Render Month Summary Cards
    renderStudentMonthSummaryGrid(data.available_months);

    // Subject Breakdown Cards
    const subCardsContainer = document.getElementById("studentSubjectCards");
    if (data.subjects && data.subjects.length > 0) {
        subCardsContainer.innerHTML = data.subjects.map(sub => `
            <div class="subject-progress-card">
                <div class="subject-card-top">
                    <div class="subject-title">${sub.subject}</div>
                    <span class="subject-pct-pill ${sub.is_low ? 'warning' : ''}">${sub.percentage}%</span>
                </div>
                <div class="progress-bar-track">
                    <div class="progress-bar-fill ${sub.is_low ? 'warning' : ''}" style="width: ${Math.min(100, sub.percentage)}%;"></div>
                </div>
                <div class="subject-card-footer">
                    <span>Attended: <strong>${sub.present}/${sub.total}</strong> classes</span>
                    <span>${sub.is_low ? '<span class="text-danger font-bold">Shortfall</span>' : '<span class="text-success font-bold">On Track</span>'}</span>
                </div>
            </div>
        `).join("");
    } else {
        subCardsContainer.innerHTML = `<div class="p-3 text-muted">No subject classes logged yet.</div>`;
    }

    // Today's Schedule Table
    document.getElementById("studentTodayDayTitle").textContent = data.today_day;
    const todayScheduleTbody = document.getElementById("studentTodayScheduleBody");
    if (data.today_schedule && data.today_schedule.length > 0) {
        todayScheduleTbody.innerHTML = data.today_schedule.map(p => `
            <tr>
                <td class="font-bold">Period ${p.period_number}</td>
                <td class="font-mono text-xs">${p.start_time} - ${p.end_time}</td>
                <td class="font-semibold text-primary">${p.subject_name}</td>
                <td>${p.faculty_name}</td>
                <td><span class="info-badge">${p.room || 'Room 301'}</span></td>
            </tr>
        `).join("");
    } else {
        todayScheduleTbody.innerHTML = `<tr><td colspan="5" class="text-center py-3 text-muted">No classes scheduled for today.</td></tr>`;
    }

    // Attendance History Log
    renderStudentHistoryTable(data.history);
}

// =============================================================================
// STUDENT VIEW MODES (OVERALL / MONTHLY / DAILY / PREDICTOR)
// =============================================================================

function switchStudentAttendanceMode(mode) {
    studentAttendanceMode = mode;

    // Toggle button active states
    document.querySelectorAll(".student-view-mode-tabs .view-mode-btn").forEach(btn => btn.classList.remove("active"));
    const activeBtn = document.getElementById(`btnMode${mode.charAt(0).toUpperCase() + mode.slice(1)}`);
    if (activeBtn) activeBtn.classList.add("active");

    const monthBar = document.getElementById("studentMonthlyControlBar");
    const dailyBar = document.getElementById("studentDailyControlBar");
    const calCard = document.getElementById("studentCalendarCard");
    const predCard = document.getElementById("studentPredictorCard");
    const monthBreakdownCard = document.getElementById("studentMonthBreakdownCard");

    if (monthBar) monthBar.classList.toggle("hidden", mode !== "monthly");
    if (dailyBar) dailyBar.classList.toggle("hidden", mode !== "daily");

    updateStudentKpiDisplay();

    // Scroll to relevant section if Daily or Predictor clicked
    if (mode === "daily" && calCard) {
        calCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else if (mode === "predictor" && predCard) {
        predCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } else if (mode === "monthly" && monthBreakdownCard) {
        monthBreakdownCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
}

function onStudentMonthSelectChange(monthKey) {
    studentSelectedMonthKey = monthKey;
    const [y, m] = monthKey.split("-");
    studentCalYear = parseInt(y, 10);
    studentCalMonth = parseInt(m, 10) - 1;
    renderStudentCalendar();
    updateStudentKpiDisplay();
}

function updateStudentKpiDisplay() {
    if (!currentStudentData) return;

    const stats = currentStudentData.stats;
    const threshold = stats.threshold || 75;
    const headerLabel = document.getElementById("studentGaugeHeaderLabel");
    const pctCircle = document.getElementById("studentGaugeCircle");
    const pctDisplay = document.getElementById("studentOverallPctDisplay");
    const standingMsg = document.getElementById("studentStandingMessage");

    const kpiTotalLabel = document.getElementById("studentKpiTotalLabel");
    const kpiAttendedLabel = document.getElementById("studentKpiAttendedLabel");
    const kpiMissedLabel = document.getElementById("studentKpiMissedLabel");

    const totalVal = document.getElementById("studentTotalClassesDisplay");
    const attendedVal = document.getElementById("studentAttendedDisplay");
    const missedVal = document.getElementById("studentMissedDisplay");

    if (studentAttendanceMode === "overall" || studentAttendanceMode === "predictor") {
        headerLabel.textContent = "Overall Attendance Rate";
        pctDisplay.textContent = `${stats.percentage}%`;
        kpiTotalLabel.textContent = "Total Classes Held";
        kpiAttendedLabel.textContent = "Classes Attended";
        kpiMissedLabel.textContent = "Classes Missed";

        totalVal.textContent = stats.total_classes;
        attendedVal.textContent = stats.present_classes;
        missedVal.textContent = stats.absent_classes;

        if (stats.is_low) {
            pctCircle.className = "gauge-pct-circle warning";
            standingMsg.innerHTML = `
                <span class="text-danger font-bold">Attendance Warning:</span> 
                Your attendance is below ${threshold}%. Attend the next <strong>${stats.shortfall} classes</strong> to reach the required standard.
            `;
        } else {
            pctCircle.className = "gauge-pct-circle";
            standingMsg.innerHTML = `
                <span class="text-success font-bold">Good Standing:</span> 
                Your attendance rate meets academic guidelines (≥ ${threshold}%). Keep it up!
            `;
        }
    } else if (studentAttendanceMode === "monthly") {
        const monthData = (currentStudentData.by_month && currentStudentData.by_month[studentSelectedMonthKey]) || {
            month_name: "Selected Month",
            percentage: 0.0,
            total_classes: 0,
            present_classes: 0,
            absent_classes: 0,
            is_low: false
        };

        headerLabel.textContent = `${monthData.month_name} Attendance Rate`;
        pctDisplay.textContent = `${monthData.percentage}%`;
        kpiTotalLabel.textContent = `${monthData.month_name} Classes`;
        kpiAttendedLabel.textContent = "Attended in Month";
        kpiMissedLabel.textContent = "Missed in Month";

        totalVal.textContent = monthData.total_classes;
        attendedVal.textContent = monthData.present_classes;
        missedVal.textContent = monthData.absent_classes;

        const infoBadge = document.getElementById("selectedMonthInfoBadge");
        if (infoBadge) {
            infoBadge.textContent = `${monthData.month_name}: ${monthData.percentage}% (${monthData.present_classes}/${monthData.total_classes} Attended)`;
        }

        if (monthData.is_low) {
            pctCircle.className = "gauge-pct-circle warning";
            standingMsg.innerHTML = `
                <span class="text-danger font-bold">Monthly Warning:</span> 
                In <strong>${monthData.month_name}</strong>, your attendance was <strong>${monthData.percentage}%</strong> (below ${threshold}%).
            `;
        } else {
            pctCircle.className = "gauge-pct-circle";
            standingMsg.innerHTML = `
                <span class="text-success font-bold">${monthData.month_name} On Track:</span> 
                You achieved <strong>${monthData.percentage}%</strong> attendance in this month.
            `;
        }
    } else if (studentAttendanceMode === "daily") {
        const dailyData = (currentStudentData.by_date && currentStudentData.by_date[studentSelectedDate]) || null;
        
        if (dailyData) {
            headerLabel.textContent = `Daily Attendance (${dailyData.day_name}, ${dailyData.formatted_date})`;
            pctDisplay.textContent = `${dailyData.percentage}%`;
            kpiTotalLabel.textContent = "Periods Held Today";
            kpiAttendedLabel.textContent = "Periods Attended";
            kpiMissedLabel.textContent = "Periods Missed";

            totalVal.textContent = dailyData.total;
            attendedVal.textContent = dailyData.present;
            missedVal.textContent = dailyData.absent;

            if (dailyData.percentage < threshold) {
                pctCircle.className = "gauge-pct-circle warning";
                standingMsg.innerHTML = `
                    <span class="text-danger font-bold">Daily Shortfall:</span> 
                    Attended <strong>${dailyData.present} of ${dailyData.total} periods</strong> on ${dailyData.formatted_date}.
                `;
            } else {
                pctCircle.className = "gauge-pct-circle";
                standingMsg.innerHTML = `
                    <span class="text-success font-bold">Full Daily Presence:</span> 
                    Attended <strong>${dailyData.present} of ${dailyData.total} periods</strong> on ${dailyData.formatted_date}.
                `;
            }

            const dailyLabel = document.getElementById("selectedDailyDateLabel");
            if (dailyLabel) dailyLabel.textContent = `${dailyData.day_name}, ${dailyData.formatted_date}`;
            
            const dailyChip = document.getElementById("selectedDailyStatusChip");
            if (dailyChip) {
                const statusClass = dailyData.status_type === 'present' ? 'success' : (dailyData.status_type === 'absent' ? 'danger' : 'warning');
                dailyChip.innerHTML = `<span class="badge-pill ${statusClass}">${dailyData.present}/${dailyData.total} Periods (${dailyData.percentage}%)</span>`;
            }
        } else {
            headerLabel.textContent = `Daily Attendance (${studentSelectedDate})`;
            pctDisplay.textContent = `0.0%`;
            totalVal.textContent = "0";
            attendedVal.textContent = "0";
            missedVal.textContent = "0";
            pctCircle.className = "gauge-pct-circle";
            standingMsg.innerHTML = `No classes were logged on <strong>${studentSelectedDate}</strong>.`;
        }
    }
}

// =============================================================================
// INTERACTIVE MONTHLY CALENDAR
// =============================================================================

function changeStudentCalMonth(delta) {
    studentCalMonth += delta;
    if (studentCalMonth < 0) {
        studentCalMonth = 11;
        studentCalYear -= 1;
    } else if (studentCalMonth > 11) {
        studentCalMonth = 0;
        studentCalYear += 1;
    }
    
    // Format month key YYYY-MM
    const mStr = String(studentCalMonth + 1).padStart(2, '0');
    studentSelectedMonthKey = `${studentCalYear}-${mStr}`;
    
    // Sync select dropdown
    const monthSelect = document.getElementById("studentMonthSelect");
    if (monthSelect) monthSelect.value = studentSelectedMonthKey;

    renderStudentCalendar();
    if (studentAttendanceMode === "monthly") {
        updateStudentKpiDisplay();
    }
}

function goStudentCalToday() {
    const now = new Date();
    studentCalYear = now.getFullYear();
    studentCalMonth = now.getMonth();
    const todayStr = now.toISOString().split("T")[0];
    studentSelectedDate = todayStr;
    const mStr = String(studentCalMonth + 1).padStart(2, '0');
    studentSelectedMonthKey = `${studentCalYear}-${mStr}`;
    
    const monthSelect = document.getElementById("studentMonthSelect");
    if (monthSelect) monthSelect.value = studentSelectedMonthKey;

    renderStudentCalendar();
    selectStudentCalendarDate(todayStr);
}

function renderStudentCalendar() {
    const monthTitle = document.getElementById("studentCalMonthTitle");
    const container = document.getElementById("studentCalDaysGrid");
    if (!container || !monthTitle) return;

    const monthNames = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ];
    monthTitle.textContent = `${monthNames[studentCalMonth]} ${studentCalYear}`;

    // First day of month (0 = Sunday, 1 = Monday, etc.)
    const firstDayIndex = new Date(studentCalYear, studentCalMonth, 1).getDay();
    // Adjust to Monday-based index (0 = Monday, 6 = Sunday)
    const startOffset = (firstDayIndex === 0) ? 6 : firstDayIndex - 1;

    const daysInMonth = new Date(studentCalYear, studentCalMonth + 1, 0).getDate();
    const todayStr = new Date().toISOString().split("T")[0];

    let cellsHtml = "";

    // Blank leading days
    for (let i = 0; i < startOffset; i++) {
        cellsHtml += `<div class="cal-day-cell empty"></div>`;
    }

    // Days in current month
    const byDate = (currentStudentData && currentStudentData.by_date) || {};

    for (let day = 1; day <= daysInMonth; day++) {
        const dStr = `${studentCalYear}-${String(studentCalMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
        const dayData = byDate[dStr];
        const isToday = (dStr === todayStr);
        const isSelected = (dStr === studentSelectedDate);

        let cellClass = "cal-day-cell";
        let badgeHtml = "";

        if (dayData) {
            if (dayData.status_type === "present") {
                cellClass += " is-present";
                badgeHtml = `<span class="cal-day-badge">✓ ${dayData.present}/${dayData.total} Present</span>`;
            } else if (dayData.status_type === "absent") {
                cellClass += " is-absent";
                badgeHtml = `<span class="cal-day-badge">✗ 0/${dayData.total} Absent</span>`;
            } else {
                cellClass += " is-partial";
                badgeHtml = `<span class="cal-day-badge">⚡ ${dayData.present}/${dayData.total} (${dayData.percentage}%)</span>`;
            }
        }

        if (isToday) cellClass += " is-today";
        if (isSelected) cellClass += " is-selected";

        cellsHtml += `
            <div class="${cellClass}" onclick="selectStudentCalendarDate('${dStr}')">
                <div class="cal-day-top">
                    <span class="cal-day-num">${day}</span>
                    ${isToday ? '<span class="cal-today-tag">Today</span>' : ''}
                </div>
                ${badgeHtml}
            </div>
        `;
    }

    container.innerHTML = cellsHtml;
}

function selectStudentCalendarDate(dateStr) {
    studentSelectedDate = dateStr;

    // Update selected class on calendar cells
    document.querySelectorAll(".cal-day-cell").forEach(cell => {
        cell.classList.remove("is-selected");
    });
    
    // Re-render calendar so is-selected is exact
    renderStudentCalendar();

    // Render Inspector Box
    const titleEl = document.getElementById("inspectorDateTitle");
    const subTitleEl = document.getElementById("inspectorDateSubtitle");
    const badgeEl = document.getElementById("inspectorDatePctBadge");
    const listEl = document.getElementById("inspectorPeriodsList");

    if (!titleEl || !listEl) return;

    const dayData = currentStudentData && currentStudentData.by_date && currentStudentData.by_date[dateStr];

    if (dayData) {
        titleEl.textContent = `${dayData.day_name}, ${dayData.formatted_date} Periods`;
        subTitleEl.textContent = `Total Classes: ${dayData.total} • Attended: ${dayData.present} • Missed: ${dayData.absent}`;
        
        const badgeClass = dayData.status_type === "present" ? "success" : (dayData.status_type === "absent" ? "danger" : "warning");
        badgeEl.innerHTML = `<span class="badge-pill ${badgeClass}">Daily: ${dayData.percentage}%</span>`;

        listEl.innerHTML = dayData.periods.map(p => `
            <div class="inspector-period-row">
                <div class="period-left-meta">
                    <span class="period-num-badge">${p.period_label}</span>
                    <div class="period-info">
                        <strong>${p.subject}</strong>
                        <small>${p.time} • ${p.faculty} ${p.topic ? '• ' + p.topic : ''}</small>
                    </div>
                </div>
                <div>
                    <span class="badge-pill ${p.status === 'Present' ? 'success' : 'danger'}">
                        ${p.status === 'Present' ? '☑ Present' : '☐ Absent'}
                    </span>
                </div>
            </div>
        `).join("");
    } else {
        titleEl.textContent = `Date: ${dateStr}`;
        subTitleEl.textContent = "No period sessions recorded for this date.";
        badgeEl.innerHTML = `<span class="badge-pill secondary">No Session</span>`;
        listEl.innerHTML = `<div class="p-3 text-center text-muted">No attendance marked for this date.</div>`;
    }

    if (studentAttendanceMode === "daily") {
        updateStudentKpiDisplay();
    }
}

// =============================================================================
// PREDICTIVE ATTENDANCE CALCULATOR / SIMULATOR
// =============================================================================

function setSimClasses(count) {
    const input = document.getElementById("simAttendCount");
    if (input) {
        input.value = count;
        calculateNextPercentage();
    }
}

function stepSimClasses(delta) {
    const input = document.getElementById("simAttendCount");
    if (input) {
        let val = parseInt(input.value, 10) || 0;
        val = Math.max(0, val + delta);
        input.value = val;
        calculateNextPercentage();
    }
}

function calculateNextPercentage() {
    if (!currentStudentData || !currentStudentData.stats) return;

    const stats = currentStudentData.stats;
    const currentPresent = stats.present_classes || 0;
    const currentTotal = stats.total_classes || 0;
    const currentPct = stats.percentage || 0.0;
    const threshold = stats.threshold || 75.0;

    const input = document.getElementById("simAttendCount");
    const count = parseInt(input ? input.value : 4, 10) || 0;

    const newPresent = currentPresent + count;
    const newTotal = currentTotal + count;
    const newPct = newTotal > 0 ? ((newPresent / newTotal) * 100) : 0.0;
    const diff = newPct - currentPct;

    const currentPctEl = document.getElementById("simCurrentPct");
    const predPctEl = document.getElementById("simPredictedPct");
    const diffBadge = document.getElementById("simDiffBadge");
    const subtextEl = document.getElementById("simResultSubtext");

    if (currentPctEl) currentPctEl.textContent = `${currentPct.toFixed(2)}%`;
    if (predPctEl) predPctEl.textContent = `${newPct.toFixed(2)}%`;

    if (diffBadge) {
        if (diff >= 0) {
            diffBadge.className = "sim-diff-badge positive";
            diffBadge.textContent = `+${diff.toFixed(2)}% Gain`;
        } else {
            diffBadge.className = "sim-diff-badge negative";
            diffBadge.textContent = `${diff.toFixed(2)}%`;
        }
    }

    if (subtextEl) {
        const thresholdReached = newPct >= threshold;
        subtextEl.innerHTML = `
            Attending the next <strong>${count} classes</strong> consecutively on upcoming dates will make your record <strong>${newPresent} / ${newTotal} classes</strong>. 
            ${thresholdReached ? '<span class="text-success font-bold">🎯 Target ' + threshold + '% Reached!</span>' : '<span class="text-warning font-bold">Still ' + (threshold - newPct).toFixed(1) + '% below threshold.</span>'}
        `;
    }
}

function setTargetPct(targetVal) {
    const input = document.getElementById("simTargetPct");
    if (input) {
        input.value = targetVal;
        calculateTargetGoal();
    }
}

function calculateTargetGoal() {
    if (!currentStudentData || !currentStudentData.stats) return;

    const stats = currentStudentData.stats;
    const currentPresent = stats.present_classes || 0;
    const currentTotal = stats.total_classes || 0;
    const currentPct = stats.percentage || 0.0;

    const input = document.getElementById("simTargetPct");
    const target = parseFloat(input ? input.value : 75) || 75.0;

    const countEl = document.getElementById("goalClassesNeeded");
    const descEl = document.getElementById("goalDescText");

    if (currentTotal === 0) {
        if (countEl) countEl.textContent = "0";
        if (descEl) descEl.textContent = "No classes logged yet.";
        return;
    }

    if (currentPct >= target) {
        if (countEl) countEl.textContent = "0";
        if (descEl) descEl.innerHTML = `You are already at <strong>${currentPct.toFixed(2)}%</strong> (Above your ${target}% target!). Keep attending regularly.`;
        return;
    }

    if (target >= 100) {
        if (countEl) countEl.textContent = "∞";
        if (descEl) descEl.textContent = "100% attendance cannot be achieved once any class is missed.";
        return;
    }

    const tRatio = target / 100.0;
    const needed = (tRatio * currentTotal - currentPresent) / (1.0 - tRatio);
    const classesRequired = Math.max(0, Math.ceil(needed));

    if (countEl) countEl.textContent = classesRequired;
    if (descEl) {
        descEl.innerHTML = `
            You need to attend the next <strong>${classesRequired} consecutive classes</strong> without missing to reach <strong>${target}%</strong> attendance.
        `;
    }
}

// =============================================================================
// MONTH-WISE BREAKDOWN CARDS
// =============================================================================

function renderStudentMonthSummaryGrid(monthsList) {
    const grid = document.getElementById("studentMonthSummaryGrid");
    if (!grid) return;

    if (!monthsList || monthsList.length === 0) {
        grid.innerHTML = `<div class="p-3 text-muted">No monthly attendance records yet.</div>`;
        return;
    }

    grid.innerHTML = monthsList.map(m => `
        <div class="month-summary-card" onclick="selectStudentMonthCard('${m.key}')">
            <div class="month-card-header">
                <span class="month-card-title">${m.name}</span>
                <span class="month-card-pct ${m.is_low ? 'danger' : ''}">${m.percentage}%</span>
            </div>
            <div class="progress-bar-track">
                <div class="progress-bar-fill ${m.is_low ? 'warning' : ''}" style="width: ${Math.min(100, m.percentage)}%;"></div>
            </div>
            <div class="month-card-meta">
                <span>Attended: <strong>${m.present}/${m.total}</strong></span>
                <span>${m.is_low ? '<span class="text-danger font-bold">Below 75%</span>' : '<span class="text-success font-bold">Good Standing</span>'}</span>
            </div>
        </div>
    `).join("");
}

function selectStudentMonthCard(monthKey) {
    studentSelectedMonthKey = monthKey;
    const [y, m] = monthKey.split("-");
    studentCalYear = parseInt(y, 10);
    studentCalMonth = parseInt(m, 10) - 1;
    
    const monthSelect = document.getElementById("studentMonthSelect");
    if (monthSelect) monthSelect.value = monthKey;

    switchStudentAttendanceMode("monthly");
    renderStudentCalendar();
}

async function loadStudentTimetable() {
    try {
        const res = await fetch("/api/student/timetable");
        const data = await res.json();
        if (data.success) {
            studentTimetableData = data.periods;
            filterStudentTimetableDay("Monday");
        }
    } catch (e) {
        console.error("Error loading student timetable:", e);
    }
}

function filterStudentTimetableDay(day) {
    document.querySelectorAll("#studentTimetableDayTabs .day-tab-btn").forEach(btn => {
        btn.classList.toggle("active", btn.textContent.trim() === day);
    });

    const dayPeriods = studentTimetableData.filter(p => p.day_of_week === day);
    const grid = document.getElementById("studentPeriodCardsGrid");
    if (!grid) return;

    if (dayPeriods.length === 0) {
        grid.innerHTML = `<div class="card p-4 text-center text-muted" style="grid-column: 1 / -1;">No periods scheduled on ${day}.</div>`;
        return;
    }

    grid.innerHTML = dayPeriods.map(p => `
        <div class="period-card">
            <div class="period-card-top">
                <span class="period-number-badge">Period ${p.period_number}</span>
                <span class="period-time-badge">${p.start_time} - ${p.end_time}</span>
            </div>
            <div class="period-subject-title">${p.subject_name}</div>
            <div class="period-meta-line">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                    <circle cx="12" cy="7" r="4"></circle>
                </svg>
                <span>${p.faculty_name}</span>
            </div>
            <div class="period-meta-line">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                </svg>
                <span>${p.room || 'Room 301'}</span>
            </div>
        </div>
    `).join("");
}

function openChangePasswordModal() {
    document.getElementById("oldPasswordInput").value = "";
    document.getElementById("newPasswordInput").value = "";
    document.getElementById("confirmPasswordInput").value = "";
    document.getElementById("changePasswordModal").classList.remove("hidden");
}

function closeChangePasswordModal() {
    document.getElementById("changePasswordModal").classList.add("hidden");
}

async function handleChangePassword(e) {
    e.preventDefault();
    const oldPwd = document.getElementById("oldPasswordInput").value.trim();
    const newPwd = document.getElementById("newPasswordInput").value.trim();
    const confirmPwd = document.getElementById("confirmPasswordInput").value.trim();

    if (newPwd !== confirmPwd) {
        showToast("New passwords do not match.", "error");
        return;
    }

    try {
        const res = await fetch("/api/student/change-password", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Password updated successfully.", "success");
            closeChangePasswordModal();
        } else {
            showToast(data.message || "Failed to update password.", "error");
        }
    } catch (err) {
        showToast("Server error updating password.", "error");
    }
}


// =============================================================================
// ATTENDANCE MARKING (CORE WORKFLOW WITH SINGLE CHECKBOX / TOGGLE)
// =============================================================================

async function loadStudentsRoster() {
    const tbody = document.getElementById("studentRosterBody");
    if (!tbody) return;

    tbody.innerHTML = `
        <tr>
            <td colspan="5" class="table-loading">
                <div class="spinner"></div>
                <span>Loading student roster from database...</span>
            </td>
        </tr>
    `;

    try {
        const section = document.getElementById("sessionSection") ? document.getElementById("sessionSection").value : "CAI-A";
        const res = await fetch(`/api/students?section=${encodeURIComponent(section)}`);
        allStudents = await res.json();

        // Initialize Attendance Map with default state if not editing
        if (!currentEditingSessionId) {
            const defState = systemSettings.default_attendance_state || "Present";
            attendanceMap = {};
            allStudents.forEach(st => {
                attendanceMap[st.roll_no] = defState;
            });
        }

        renderAttendanceRosterTable();
        updateLiveAttendanceSummary();
        checkIfSessionAlreadyExists();

    } catch (e) {
        console.error("Error loading students:", e);
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger py-4">Failed to load student roster.</td></tr>`;
    }
}

function onSectionChange() {
    currentEditingSessionId = null;
    document.getElementById("sessionModeBadge").textContent = "New Session";
    document.getElementById("sessionModeBadge").className = "session-badge";
    document.getElementById("saveBtnText").textContent = "Save Attendance Record";
    document.getElementById("existingSessionNotice").classList.add("hidden");
    loadStudentsRoster();
    updateCtpoPeriodLink();
}

async function onSessionConfigChange() {
    checkIfSessionAlreadyExists();
}

async function checkIfSessionAlreadyExists() {
    const date = document.getElementById("sessionDate").value;
    const subject = document.getElementById("sessionSubject").value;
    const section = document.getElementById("sessionSection").value;
    const period = document.getElementById("sessionPeriod").value;

    if (!date || !subject || !section || !period) return;

    try {
        const res = await fetch(`/api/attendance/check?date=${date}&subject=${encodeURIComponent(subject)}&section=${encodeURIComponent(section)}&period=${period}`);
        const data = await res.json();

        const notice = document.getElementById("existingSessionNotice");
        const badge = document.getElementById("sessionModeBadge");
        const saveBtnText = document.getElementById("saveBtnText");

        if (data.exists) {
            notice.classList.remove("hidden");
            currentEditingSessionId = data.session_id;
            badge.textContent = `Editing Session #${data.session_id}`;
            badge.className = "session-badge editing";
            saveBtnText.textContent = "Update Attendance";

            loadSessionIntoMarkingView(data.session_id, false);
        } else {
            if (!currentEditingSessionId) {
                notice.classList.add("hidden");
                badge.textContent = "New Session";
                badge.className = "session-badge";
                saveBtnText.textContent = "Save CTPO Attendance";
            }
        }
    } catch (e) {
        console.error("Error checking session existence:", e);
    }
}

function renderAttendanceRosterTable() {
    const tbody = document.getElementById("studentRosterBody");
    if (!tbody) return;

    const searchInput = document.getElementById("studentSearchInput");
    const searchVal = (searchInput ? searchInput.value : "").trim().toLowerCase();
    
    tbody.innerHTML = "";
    let visibleCount = 0;

    allStudents.forEach((student, index) => {
        const rollNo = student.roll_no;
        const name = student.name;
        const status = attendanceMap[rollNo] || "Present";
        const isPresent = (status === "Present");

        if (searchVal) {
            const matchesSearch = name.toLowerCase().includes(searchVal) || rollNo.toLowerCase().includes(searchVal);
            if (!matchesSearch) return;
        }

        if (activeRosterFilter === "present" && !isPresent) return;
        if (activeRosterFilter === "absent" && isPresent) return;

        visibleCount++;

        const termRate = student.attendance_percentage !== undefined ? `${student.attendance_percentage}%` : "--";
        const isLow = student.is_low;

        const row = document.createElement("tr");
        row.id = `row-${rollNo}`;
        row.className = isPresent ? "row-present" : "row-absent";

        row.innerHTML = `
            <td style="text-align: center; color: var(--text-muted);">${index + 1}</td>
            <td class="roll-number-cell">${rollNo}</td>
            <td class="student-name-cell">${name}</td>
            <td style="text-align: center;">
                <span class="badge-pill ${isLow ? 'danger' : 'success'}">${termRate}</span>
            </td>
            <td style="text-align: center;">
                <div class="attendance-toggle-wrap">
                    <label class="attendance-toggle-label ${isPresent ? 'is-present' : 'is-absent'}" id="toggle-label-${rollNo}">
                        <input
                            type="checkbox"
                            id="check-${rollNo}"
                            ${isPresent ? 'checked' : ''}
                            onchange="onAttendanceCheckboxChange('${rollNo}', this.checked)"
                        >
                        <div class="custom-checkbox-indicator">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5">
                                <polyline points="20 6 9 17 4 12"></polyline>
                            </svg>
                        </div>
                        <span class="toggle-status-text" id="status-text-${rollNo}">
                            ${isPresent ? '☑ Present' : '☐ Absent'}
                        </span>
                    </label>
                </div>
            </td>
        `;

        tbody.appendChild(row);
    });

    const visCountEl = document.getElementById("visibleRosterCount");
    const totCountEl = document.getElementById("totalRosterCount");
    if (visCountEl) visCountEl.textContent = visibleCount;
    if (totCountEl) totCountEl.textContent = allStudents.length;

    if (visibleCount === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; padding: 32px; color: var(--text-muted);">
                    No students found matching current criteria.
                </td>
            </tr>
        `;
    }
}

// Single Checkbox / Toggle Handler
function onAttendanceCheckboxChange(rollNo, isChecked) {
    const newStatus = isChecked ? "Present" : "Absent";
    attendanceMap[rollNo] = newStatus;

    const row = document.getElementById(`row-${rollNo}`);
    const label = document.getElementById(`toggle-label-${rollNo}`);
    const statusText = document.getElementById(`status-text-${rollNo}`);

    if (row && label && statusText) {
        if (isChecked) {
            row.className = "row-present";
            label.className = "attendance-toggle-label is-present";
            statusText.textContent = "☑ Present";
        } else {
            row.className = "row-absent";
            label.className = "attendance-toggle-label is-absent";
            statusText.textContent = "☐ Absent";
        }
    }

    updateLiveAttendanceSummary();

    if (activeRosterFilter !== 'all') {
        renderAttendanceRosterTable();
    }
}

// Live summary calculation
function updateLiveAttendanceSummary() {
    const total = allStudents.length;
    let presentCount = 0;

    allStudents.forEach(st => {
        if (attendanceMap[st.roll_no] === "Present") {
            presentCount++;
        }
    });

    const absentCount = total - presentCount;
    const percentage = total > 0 ? ((presentCount / total) * 100).toFixed(2) : "0.00";

    const totalEl = document.getElementById("liveTotalStudents");
    const presEl = document.getElementById("livePresentCount");
    const absEl = document.getElementById("liveAbsentCount");
    const pctEl = document.getElementById("liveAttendancePercent");

    if (totalEl) totalEl.textContent = total;
    if (presEl) presEl.textContent = presentCount;
    if (absEl) absEl.textContent = absentCount;
    if (pctEl) pctEl.textContent = `${percentage}%`;

    const fAll = document.getElementById("filterCountAll");
    const fPres = document.getElementById("filterCountPresent");
    const fAbs = document.getElementById("filterCountAbsent");

    if (fAll) fAll.textContent = total;
    if (fPres) fPres.textContent = presentCount;
    if (fAbs) fAbs.textContent = absentCount;

    const threshFlag = document.getElementById("liveThresholdFlag");
    const thresh = parseFloat(systemSettings.low_attendance_threshold || 75.0);
    if (threshFlag) {
        if (parseFloat(percentage) < thresh && total > 0) {
            threshFlag.textContent = `⚠️ Below ${thresh}%`;
            threshFlag.className = "threshold-indicator text-danger font-bold text-xs";
        } else {
            threshFlag.textContent = `✓ Regular`;
            threshFlag.className = "threshold-indicator text-success font-bold text-xs";
        }
    }
}

function markAllPresent() {
    allStudents.forEach(st => {
        attendanceMap[st.roll_no] = "Present";
    });
    renderAttendanceRosterTable();
    updateLiveAttendanceSummary();
    showToast("All students marked Present.", "info");
}

function clearAllAttendance() {
    allStudents.forEach(st => {
        attendanceMap[st.roll_no] = "Absent";
    });
    renderAttendanceRosterTable();
    updateLiveAttendanceSummary();
    showToast("All students marked Absent.", "warning");
}

function invertSelection() {
    allStudents.forEach(st => {
        const curr = attendanceMap[st.roll_no] || "Present";
        attendanceMap[st.roll_no] = (curr === "Present") ? "Absent" : "Present";
    });
    renderAttendanceRosterTable();
    updateLiveAttendanceSummary();
}

function setRosterFilter(filterType) {
    activeRosterFilter = filterType;
    document.querySelectorAll(".filter-pills .pill").forEach(p => {
        p.classList.toggle("active", p.dataset.filter === filterType);
    });
    renderAttendanceRosterTable();
}

function filterRosterTable() {
    const searchVal = document.getElementById("studentSearchInput").value;
    const clearBtn = document.getElementById("clearSearchBtn");
    if (clearBtn) clearBtn.classList.toggle("hidden", !searchVal);
    renderAttendanceRosterTable();
}

function clearSearch() {
    document.getElementById("studentSearchInput").value = "";
    document.getElementById("clearSearchBtn").classList.add("hidden");
    renderAttendanceRosterTable();
}

function resetToNewSession() {
    currentEditingSessionId = null;
    document.getElementById("sessionModeBadge").textContent = "New Session";
    document.getElementById("sessionModeBadge").className = "session-badge";
    document.getElementById("saveBtnText").textContent = "Save CTPO Attendance";
    document.getElementById("existingSessionNotice").classList.add("hidden");
    document.getElementById("sessionTopic").value = "";
    
    const def = systemSettings.default_attendance_state || "Present";
    allStudents.forEach(st => {
        attendanceMap[st.roll_no] = def;
    });
    renderAttendanceRosterTable();
    updateLiveAttendanceSummary();
    showToast("Ready for new period session.", "info");
}


// =============================================================================
// SAVE ATTENDANCE SESSION
// =============================================================================

async function saveAttendanceRecord(forceOverwrite = false) {
    const date = document.getElementById("sessionDate").value;
    const subject = document.getElementById("sessionSubject").value;
    const section = document.getElementById("sessionSection").value;
    const period = document.getElementById("sessionPeriod").value;
    const topic = document.getElementById("sessionTopic").value;

    if (!date) {
        showToast("Please select a date.", "error");
        return;
    }
    if (!subject) {
        showToast("Please select a subject.", "error");
        return;
    }
    if (!section) {
        showToast("Please select a section.", "error");
        return;
    }

    if (Object.keys(attendanceMap).length === 0) {
        showToast("No students loaded to mark attendance.", "error");
        return;
    }

    const saveBtn = document.getElementById("saveAttendanceBtn");
    saveBtn.disabled = true;
    saveBtn.classList.add("btn-loading");

    const payload = {
        date: date,
        subject_name: subject,
        section: section,
        period: period,
        topic: topic,
        faculty_name: (currentUser.role === 'ctpo') ? 'CTPO Incharge' : (currentUser.full_name || 'Faculty Incharge'),
        records: attendanceMap,
        session_id: currentEditingSessionId,
        force_overwrite: forceOverwrite
    };

    try {
        const response = await fetch("/api/attendance/session", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.status === 409 && result.conflict) {
            saveBtn.disabled = false;
            saveBtn.classList.remove("btn-loading");

            showConfirm(
                "Session Already Exists",
                `An attendance record for ${date}, ${subject}, ${section}, Period ${period} already exists. Do you want to update it?`,
                () => {
                    currentEditingSessionId = result.session_id;
                    saveAttendanceRecord(true);
                }
            );
            return;
        }

        if (result.success) {
            lastSavedSession = result;
            currentEditingSessionId = result.session_id;

            document.getElementById("sessionModeBadge").textContent = `Editing Session #${result.session_id}`;
            document.getElementById("sessionModeBadge").className = "session-badge editing";
            document.getElementById("saveBtnText").textContent = "Update Attendance";

            showToast("Attendance saved successfully.", "success");
            openSaveSuccessModal(result);

            loadDashboardStats();
            loadAttendanceHistory();
            loadLowAttendanceData();
        } else {
            showToast(result.message || "Unable to save attendance.", "error");
        }

    } catch (e) {
        console.error("Save error:", e);
        showToast("Unable to save attendance. Network/server error.", "error");
    } finally {
        saveBtn.disabled = false;
        saveBtn.classList.remove("btn-loading");
    }
}

function openSaveSuccessModal(data) {
    document.getElementById("savedDateVal").textContent = data.date;
    document.getElementById("savedSubjectVal").textContent = data.subject;
    document.getElementById("savedSecPeriodVal").textContent = `${data.section} • Period ${data.period}`;
    document.getElementById("savedTotalVal").textContent = data.total_students;
    document.getElementById("savedPresentVal").textContent = data.present_count;
    document.getElementById("savedAbsentVal").textContent = data.absent_count;
    document.getElementById("savedPercentageVal").textContent = `${data.percentage}%`;

    document.getElementById("savedPresentCountBadge").textContent = data.present_students.length;
    document.getElementById("savedAbsentCountBadge").textContent = data.absent_students.length;

    const presentListEl = document.getElementById("savedPresentList");
    presentListEl.innerHTML = data.present_students.map(s => `
        <div class="breakdown-item">
            <span class="roll">${s.roll_no}</span>
            <span>${s.name}</span>
        </div>
    `).join("") || `<div class="p-2 text-muted">No students present</div>`;

    const absentListEl = document.getElementById("savedAbsentList");
    absentListEl.innerHTML = data.absent_students.map(s => `
        <div class="breakdown-item">
            <span class="roll text-danger">${s.roll_no}</span>
            <span>${s.name}</span>
        </div>
    `).join("") || `<div class="p-2 text-muted">No students absent (100% Present)</div>`;

    document.getElementById("saveSuccessModal").classList.remove("hidden");
}

function closeSaveSuccessModal() {
    document.getElementById("saveSuccessModal").classList.add("hidden");
}

function exportSavedSession(format) {
    if (!lastSavedSession || !lastSavedSession.session_id) {
        showToast("No active session to export.", "error");
        return;
    }
    window.open(`/api/export/session/${lastSavedSession.session_id}/${format}`, '_blank');
}

async function loadSessionIntoMarkingView(sessionId, switchView = true) {
    try {
        const res = await fetch(`/api/attendance/session/${sessionId}`);
        const data = await res.json();

        if (!data.success) {
            showToast("Failed to load session details.", "error");
            return;
        }

        const session = data.session;
        document.getElementById("sessionDate").value = session.date;
        document.getElementById("sessionSubject").value = session.subject_name;
        document.getElementById("sessionSection").value = session.section;
        document.getElementById("sessionPeriod").value = session.period;
        document.getElementById("sessionTopic").value = session.topic || "";

        currentEditingSessionId = session.id;
        document.getElementById("sessionModeBadge").textContent = `Editing Session #${session.id}`;
        document.getElementById("sessionModeBadge").className = "session-badge editing";
        document.getElementById("saveBtnText").textContent = "Update Attendance";

        attendanceMap = data.records;

        renderAttendanceRosterTable();
        updateLiveAttendanceSummary();

        if (switchView) {
            switchTab("mark-attendance");
            showToast(`Loaded Session #${session.id} for editing.`, "info");
        }

    } catch (e) {
        console.error("Error loading session:", e);
    }
}


// =============================================================================
// DASHBOARD OVERVIEW METRICS & STATS
// =============================================================================

async function loadDashboardStats() {
    try {
        const res = await fetch("/api/dashboard");
        const data = await res.json();

        const todaySessEl = document.getElementById("dashTodaySessions");
        if (todaySessEl) {
            todaySessEl.textContent = data.today_sessions_count;
            document.getElementById("dashTodayRate").textContent = `${data.today_percentage}% Today Avg`;
            document.getElementById("dashTotalStudents").textContent = data.students;
            document.getElementById("dashOverallRate").textContent = `${data.percentage}%`;
            document.getElementById("dashTotalClassesConducted").textContent = `${data.total_sessions} Classes Logged`;

            document.getElementById("dashLowCount").textContent = data.low_attendance_count;
            document.getElementById("dashThresholdText").textContent = `Below ${data.threshold}% Threshold`;
            const lowBadge = document.getElementById("navLowBadge");
            if (lowBadge) lowBadge.textContent = data.low_attendance_count;

            const recentTbody = document.getElementById("dashRecentSessionsBody");
            if (data.recent_sessions && data.recent_sessions.length > 0) {
                recentTbody.innerHTML = data.recent_sessions.map(s => `
                    <tr>
                        <td class="font-semibold">${s.date}</td>
                        <td>${s.subject_name}</td>
                        <td>${s.section} • P${s.period}</td>
                        <td style="text-align: center;">${s.total}</td>
                        <td style="text-align: center;" class="text-present font-bold">${s.present}</td>
                        <td style="text-align: center;">
                            <span class="badge-pill ${s.percentage < data.threshold ? 'danger' : 'success'}">${s.percentage}%</span>
                        </td>
                        <td>
                            <button class="btn btn-sm btn-outline-primary" onclick="loadSessionIntoMarkingView(${s.id})">Edit</button>
                        </td>
                    </tr>
                `).join("");
            } else {
                recentTbody.innerHTML = `<tr><td colspan="7" class="text-center py-3 text-muted">No attendance sessions recorded yet.</td></tr>`;
            }

            const lowContainer = document.getElementById("dashLowAttendanceContainer");
            if (data.low_students && data.low_students.length > 0) {
                lowContainer.innerHTML = data.low_students.slice(0, 6).map(st => `
                    <div class="dash-low-item">
                        <div class="student-meta">
                            <strong>${st.name}</strong>
                            <div>${st.roll_no} • ${st.section} (${st.present}/${st.total} classes)</div>
                        </div>
                        <div class="rate-badge">${st.percentage}%</div>
                    </div>
                `).join("");
            } else {
                lowContainer.innerHTML = `<div class="p-3 text-center text-muted">🎉 No students currently have low attendance!</div>`;
            }
        }

    } catch (e) {
        console.error("Error loading dashboard stats:", e);
    }
}


// =============================================================================
// ATTENDANCE HISTORY
// =============================================================================

async function loadAttendanceHistory() {
    const tbody = document.getElementById("historyTableBody");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="11" class="table-loading"><div class="spinner"></div><span>Loading history...</span></td></tr>`;

    try {
        const from = document.getElementById("histDateFrom").value;
        const to = document.getElementById("histDateTo").value;
        const subject = document.getElementById("histSubject").value;
        const section = document.getElementById("histSection").value;
        const period = document.getElementById("histPeriod") ? document.getElementById("histPeriod").value : "";
        const search = document.getElementById("histSearch").value;

        const params = new URLSearchParams();
        if (from) params.append("date_from", from);
        if (to) params.append("date_to", to);
        if (subject) params.append("subject", subject);
        if (section) params.append("section", section);
        if (period) params.append("period", period);
        if (search) params.append("search", search);

        const res = await fetch(`/api/attendance/history?${params.toString()}`);
        const sessions = await res.json();

        document.getElementById("historySessionsCount").textContent = `${sessions.length} Sessions`;

        if (sessions.length === 0) {
            tbody.innerHTML = `<tr><td colspan="11" class="text-center py-4 text-muted">No attendance history records match your filters.</td></tr>`;
            return;
        }

        tbody.innerHTML = sessions.map(s => `
            <tr>
                <td class="font-bold">${s.date}</td>
                <td>${s.subject_name}</td>
                <td><span class="info-badge">${s.section}</span></td>
                <td style="text-align: center;">Period ${s.period}</td>
                <td>${s.topic || "-"}</td>
                <td>${s.faculty_name}</td>
                <td style="text-align: center;">${s.total_students}</td>
                <td style="text-align: center;" class="text-present font-bold">${s.present_count}</td>
                <td style="text-align: center;" class="text-absent font-bold">${s.absent_count}</td>
                <td style="text-align: center;">
                    <span class="badge-pill ${s.percentage < systemSettings.low_attendance_threshold ? 'danger' : 'success'}">${s.percentage}%</span>
                </td>
                <td style="text-align: center;">
                    <div style="display: flex; gap: 4px; justify-content: center;">
                        <button class="btn btn-sm btn-outline-secondary" onclick="openSessionDetailsModal(${s.id})" title="View Details">👁️</button>
                        <button class="btn btn-sm btn-outline-primary" onclick="loadSessionIntoMarkingView(${s.id})" title="Edit Attendance">✏️</button>
                        <button class="btn btn-sm btn-outline-success" onclick="window.open('/api/export/session/${s.id}/pdf', '_blank')" title="PDF">📄</button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteSessionConfirm(${s.id}, '${s.date}', '${escapeHtml(s.subject_name)}')" title="Delete">🗑️</button>
                    </div>
                </td>
            </tr>
        `).join("");

    } catch (e) {
        console.error("Error loading history:", e);
        tbody.innerHTML = `<tr><td colspan="11" class="text-center py-4 text-danger">Failed to load attendance history.</td></tr>`;
    }
}

function resetHistoryFilters() {
    document.getElementById("histDateFrom").value = "";
    document.getElementById("histDateTo").value = "";
    document.getElementById("histSubject").value = "";
    document.getElementById("histSection").value = "";
    if (document.getElementById("histPeriod")) document.getElementById("histPeriod").value = "";
    document.getElementById("histSearch").value = "";
    loadAttendanceHistory();
}

function deleteSessionConfirm(sessionId, date, subject) {
    showConfirm("Delete Attendance Session", `Are you sure you want to permanently delete the attendance session for ${subject} on ${date}? This action cannot be undone.`, async () => {
        try {
            const res = await fetch(`/api/attendance/session/${sessionId}`, { method: "DELETE" });
            const data = await res.json();
            if (data.success) {
                showToast("Session deleted successfully.", "success");
                loadAttendanceHistory();
                loadDashboardStats();
            } else {
                showToast(data.message || "Failed to delete session.", "error");
            }
        } catch (e) {
            showToast("Server error deleting session.", "error");
        }
    });
}


// =============================================================================
// SESSION DETAILS MODAL VIEW
// =============================================================================

async function openSessionDetailsModal(sessionId) {
    try {
        const res = await fetch(`/api/attendance/session/${sessionId}`);
        const data = await res.json();
        if (!data.success) {
            showToast("Failed to fetch session details.", "error");
            return;
        }

        const s = data.session;
        document.getElementById("modalSessionTitle").textContent = `${s.subject_name} • ${s.section}`;
        document.getElementById("modalSessionSubtitle").textContent = `Date: ${s.date} | Period ${s.period} | Faculty: ${s.faculty_name}`;
        
        document.getElementById("modalSessionTotal").textContent = s.total_students;
        document.getElementById("modalSessionPresent").textContent = s.present_count;
        document.getElementById("modalSessionAbsent").textContent = s.absent_count;
        document.getElementById("modalSessionRate").textContent = `${s.percentage}%`;

        document.getElementById("modalPresentCount").textContent = data.present_students.length;
        document.getElementById("modalAbsentCount").textContent = data.absent_students.length;

        document.getElementById("modalPresentList").innerHTML = data.present_students.map(st => `
            <div class="breakdown-item">
                <span class="roll font-bold">${st.roll_no}</span>
                <span>${st.name}</span>
            </div>
        `).join("") || `<div class="p-2 text-muted">None</div>`;

        document.getElementById("modalAbsentList").innerHTML = data.absent_students.map(st => `
            <div class="breakdown-item">
                <span class="roll font-bold text-danger">${st.roll_no}</span>
                <span>${st.name}</span>
            </div>
        `).join("") || `<div class="p-2 text-muted">None (100% Present)</div>`;

        document.getElementById("modalExportPdfBtn").onclick = () => window.open(`/api/export/session/${s.id}/pdf`, '_blank');
        document.getElementById("modalExportExcelBtn").onclick = () => window.open(`/api/export/session/${s.id}/excel`, '_blank');
        document.getElementById("modalExportCsvBtn").onclick = () => window.open(`/api/export/session/${s.id}/csv`, '_blank');

        document.getElementById("sessionDetailsModal").classList.remove("hidden");

    } catch (e) {
        showToast("Error opening session modal.", "error");
    }
}

function closeSessionDetailsModal() {
    document.getElementById("sessionDetailsModal").classList.add("hidden");
}


// =============================================================================
// STUDENT ATTENDANCE PROFILE & CHECKER
// =============================================================================

function populateStudentProfileDropdown() {
    const select = document.getElementById("profileStudentSelect");
    if (!select) return;
    select.innerHTML = `<option value="">-- Choose Student to View Complete Attendance Record --</option>` +
        allStudents.map(s => `<option value="${s.roll_no}">${s.roll_no} - ${s.name} (${s.section})</option>`).join("");
}

function onStudentProfileSelected() {
    const rollNo = document.getElementById("profileStudentSelect").value;
    if (rollNo) {
        loadStudentProfile(rollNo);
    }
}

function searchStudentProfileByRoll() {
    const roll = document.getElementById("profileRollSearch").value.trim();
    if (roll) {
        loadStudentProfile(roll);
    }
}

async function loadStudentProfile(rollNo) {
    try {
        const res = await fetch(`/api/attendance/student/${encodeURIComponent(rollNo)}`);
        const data = await res.json();

        if (!data.success) {
            showToast("Student not found.", "error");
            return;
        }

        const student = data.student;
        const stats = data.stats;

        document.getElementById("studentProfileDetails").classList.remove("hidden");

        document.getElementById("profStudentName").textContent = student.name;
        document.getElementById("profRollNo").textContent = student.roll_no;
        document.getElementById("profDeptSec").textContent = `${student.department} • Section ${student.section}`;
        document.getElementById("profAvatar").textContent = student.name.substring(0, 2).toUpperCase();

        document.getElementById("profTotalClasses").textContent = stats.total_classes;
        document.getElementById("profPresentClasses").textContent = stats.present_classes;
        document.getElementById("profAbsentClasses").textContent = stats.absent_classes;
        document.getElementById("profPercentage").textContent = `${stats.percentage}%`;

        const badge = document.getElementById("profStandingBadge");
        if (stats.is_low) {
            badge.className = "badge-pill danger";
            badge.textContent = `⚠️ Low Attendance (<${stats.threshold}%)`;
        } else {
            badge.className = "badge-pill success";
            badge.textContent = `✓ Regular Standing (≥${stats.threshold}%)`;
        }

        const subjBody = document.getElementById("profSubjectTableBody");
        if (data.subjects && data.subjects.length > 0) {
            subjBody.innerHTML = data.subjects.map(sub => `
                <tr>
                    <td class="font-semibold">${sub.subject}</td>
                    <td style="text-align: center;">${sub.total}</td>
                    <td style="text-align: center;" class="text-present font-bold">${sub.present}</td>
                    <td style="text-align: center;">
                        <span class="badge-pill ${sub.is_low ? 'danger' : 'success'}">${sub.percentage}%</span>
                    </td>
                    <td style="text-align: center;">
                        <span class="${sub.is_low ? 'text-danger font-bold' : 'text-success font-bold'}">
                            ${sub.is_low ? 'Low' : 'Good'}
                        </span>
                    </td>
                </tr>
            `).join("");
        } else {
            subjBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-3">No subjects recorded yet.</td></tr>`;
        }

        const histBody = document.getElementById("profHistoryTableBody");
        if (data.history && data.history.length > 0) {
            histBody.innerHTML = data.history.map(h => `
                <tr>
                    <td>${h.date}</td>
                    <td>${h.subject}</td>
                    <td>${h.period}</td>
                    <td>
                        <span class="badge-pill ${h.status === 'Present' ? 'success' : 'danger'}">
                            ${h.status === 'Present' ? '☑ Present' : '☐ Absent'}
                        </span>
                    </td>
                </tr>
            `).join("");
        } else {
            histBody.innerHTML = `<tr><td colspan="4" class="text-center text-muted py-3">No individual sessions logged yet.</td></tr>`;
        }

    } catch (e) {
        console.error("Error loading student profile:", e);
        showToast("Error retrieving student profile.", "error");
    }
}


// =============================================================================
// LOW ATTENDANCE ALERTS & DEFAULTER REPORTS
// =============================================================================

async function loadLowAttendanceData() {
    const tbody = document.getElementById("lowStudentsTableBody");
    if (!tbody) return;

    tbody.innerHTML = `<tr><td colspan="10" class="table-loading"><div class="spinner"></div><span>Loading defaulters...</span></td></tr>`;

    try {
        const res = await fetch("/api/attendance/low");
        const defaulters = await res.json();

        const thresh = systemSettings.low_attendance_threshold || 75.0;
        document.getElementById("lowAlertThresholdDisplay").textContent = `${thresh}%`;
        document.getElementById("lowDefaultersCountBadge").textContent = `${defaulters.length} Students`;
        document.getElementById("exportDefaulterThresh").textContent = `${thresh}%`;

        if (defaulters.length === 0) {
            tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4 text-success font-bold">🎉 All students currently meet the attendance requirement (${thresh}%).</td></tr>`;
            return;
        }

        tbody.innerHTML = defaulters.map((st, idx) => `
            <tr>
                <td style="text-align: center;">${idx + 1}</td>
                <td class="roll-number-cell">${st.roll_no}</td>
                <td class="font-bold">${st.name}</td>
                <td><span class="info-badge">${st.section}</span></td>
                <td style="text-align: center;">${st.total}</td>
                <td style="text-align: center;" class="text-present font-bold">${st.present}</td>
                <td style="text-align: center;" class="text-absent font-bold">${st.absent}</td>
                <td style="text-align: center;">
                    <span class="badge-pill danger font-bold">${st.percentage}%</span>
                </td>
                <td style="text-align: center;">
                    <span class="badge-pill warning font-bold">Needs +${st.shortfall} classes</span>
                </td>
                <td style="text-align: center;">
                    <button class="btn btn-sm btn-outline-primary" onclick="viewStudentProfileDirect('${st.roll_no}')">View Profile</button>
                </td>
            </tr>
        `).join("");

    } catch (e) {
        console.error("Error loading low attendance:", e);
        tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4 text-danger">Failed to load low attendance data.</td></tr>`;
    }
}

function viewStudentProfileDirect(rollNo) {
    switchTab("student-profile");
    const pSelect = document.getElementById("profileStudentSelect");
    if (pSelect) pSelect.value = rollNo;
    loadStudentProfile(rollNo);
}

function exportDefaultersReport(format) {
    window.open(`/api/export/cumulative/${format}?only_low=true`, '_blank');
}


// =============================================================================
// EXPORT & REPORTS CENTER
// =============================================================================

async function populateExportSessionDropdown() {
    try {
        const res = await fetch("/api/attendance/history");
        const sessions = await res.json();
        const select = document.getElementById("exportSessionSelect");
        if (!select) return;

        select.innerHTML = sessions.map(s => 
            `<option value="${s.id}">${s.date} - ${s.subject_name} (${s.section}, P${s.period}) [${s.percentage}%]</option>`
        ).join("");
    } catch (e) {
        console.error("Error loading export sessions:", e);
    }
}

function exportCumulative(format) {
    const sec = document.getElementById("exportCumSection") ? document.getElementById("exportCumSection").value : "";
    const url = `/api/export/cumulative/${format}?section=${encodeURIComponent(sec)}`;
    window.open(url, '_blank');
}

function exportSelectedSessionDirect(format) {
    const sessionId = document.getElementById("exportSessionSelect").value;
    if (!sessionId) {
        showToast("Please select a session to export.", "warning");
        return;
    }
    window.open(`/api/export/session/${sessionId}/${format}`, '_blank');
}


// =============================================================================
// ROSTER & SUBJECTS ADMIN MANAGEMENT
// =============================================================================

async function loadAdminRoster() {
    const tbody = document.getElementById("adminRosterTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="8" class="table-loading"><div class="spinner"></div><span>Loading roster...</span></td></tr>`;

    try {
        const res = await fetch("/api/students");
        const students = await res.json();

        document.getElementById("rosterTotalBadge").textContent = `${students.length} Students`;

        tbody.innerHTML = students.map((st, idx) => `
            <tr>
                <td style="text-align: center;">${idx + 1}</td>
                <td class="roll-number-cell">${st.roll_no}</td>
                <td class="font-bold">${st.name}</td>
                <td>${st.department}</td>
                <td><span class="info-badge">${st.section}</span></td>
                <td style="text-align: center;">${st.total_classes}</td>
                <td style="text-align: center;">
                    <span class="badge-pill ${st.is_low ? 'danger' : 'success'}">${st.attendance_percentage}%</span>
                </td>
                <td style="text-align: center;">
                    <div style="display: flex; gap: 4px; justify-content: center;">
                        <button class="btn btn-sm btn-outline-primary" onclick="viewStudentProfileDirect('${st.roll_no}')">Profile</button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteStudentRecord('${st.roll_no}')">Delete</button>
                    </div>
                </td>
            </tr>
        `).join("");

    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4 text-danger">Failed to load admin roster.</td></tr>`;
    }
}

function filterAdminRosterTable() {
    const val = document.getElementById("rosterSearchInput").value.toLowerCase();
    const rows = document.querySelectorAll("#adminRosterTableBody tr");
    rows.forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(val) ? "" : "none";
    });
}

function openAddStudentModal() {
    document.getElementById("addStudentModal").classList.remove("hidden");
}

function closeAddStudentModal() {
    document.getElementById("addStudentModal").classList.add("hidden");
}

async function handleAddStudent(e) {
    e.preventDefault();
    const roll = document.getElementById("newStudentRoll").value.trim();
    const name = document.getElementById("newStudentName").value.trim();
    const dept = document.getElementById("newStudentDept").value.trim();
    const sec = document.getElementById("newStudentSection").value.trim();

    try {
        const res = await fetch("/api/students", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ roll_no: roll, name: name, department: dept, section: sec })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Student added successfully.", "success");
            closeAddStudentModal();
            loadStudentsRoster();
            loadAdminRoster();
        } else {
            showToast(data.message || "Failed to add student.", "error");
        }
    } catch (err) {
        showToast("Error adding student.", "error");
    }
}

function deleteStudentRecord(rollNo) {
    showConfirm("Delete Student", `Are you sure you want to delete student ${rollNo} and remove their attendance history?`, async () => {
        try {
            const res = await fetch(`/api/students/${encodeURIComponent(rollNo)}`, { method: "DELETE" });
            const data = await res.json();
            if (data.success) {
                showToast("Student deleted.", "success");
                loadStudentsRoster();
                loadAdminRoster();
            } else {
                showToast(data.message, "error");
            }
        } catch (e) {
            showToast("Server error deleting student.", "error");
        }
    });
}

function openAddSubjectModal() {
    document.getElementById("addSubjectModal").classList.remove("hidden");
}

function closeAddSubjectModal() {
    document.getElementById("addSubjectModal").classList.add("hidden");
}

async function handleAddSubject(e) {
    e.preventDefault();
    const code = document.getElementById("newSubjectCode").value.trim();
    const name = document.getElementById("newSubjectName").value.trim();
    const dept = document.getElementById("newSubjectDept").value.trim();
    const sem = document.getElementById("newSubjectSem").value.trim();

    try {
        const res = await fetch("/api/subjects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code: code, name: name, department: dept, semester: sem })
        });
        const data = await res.json();
        if (data.success) {
            showToast("Subject added.", "success");
            closeAddSubjectModal();
            loadSubjects();
        } else {
            showToast(data.message, "error");
        }
    } catch (err) {
        showToast("Error adding subject.", "error");
    }
}


// =============================================================================
// SYSTEM SETTINGS
// =============================================================================

async function loadSettingsForm() {
    try {
        const res = await fetch("/api/settings");
        const settings = await res.json();

        const colEl = document.getElementById("settingCollegeName");
        const depEl = document.getElementById("settingDeptName");
        const thrEl = document.getElementById("settingThreshold");
        const defEl = document.getElementById("settingDefaultState");

        if (colEl) colEl.value = settings.college_name || "";
        if (depEl) depEl.value = settings.department_name || "";
        if (thrEl) thrEl.value = settings.low_attendance_threshold || 75;
        if (defEl) defEl.value = settings.default_attendance_state || "Present";

    } catch (e) {
        console.error("Error loading settings:", e);
    }
}

async function saveSystemSettings(e) {
    e.preventDefault();
    const payload = {
        college_name: document.getElementById("settingCollegeName").value,
        department_name: document.getElementById("settingDeptName").value,
        low_attendance_threshold: document.getElementById("settingThreshold").value,
        default_attendance_state: document.getElementById("settingDefaultState").value
    };

    try {
        const res = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            systemSettings.low_attendance_threshold = parseFloat(payload.low_attendance_threshold);
            systemSettings.college_name = payload.college_name;
            systemSettings.department_name = payload.department_name;
            systemSettings.default_attendance_state = payload.default_attendance_state;

            renderUserHeader();
            updateLiveAttendanceSummary();
            showToast("System settings saved successfully.", "success");
        } else {
            showToast(data.message || "Failed to save settings.", "error");
        }
    } catch (err) {
        showToast("Server error updating settings.", "error");
    }
}


// =============================================================================
// REUSABLE CONFIRMATION MODAL & TOAST SYSTEM
// =============================================================================

function showConfirm(title, message, onConfirm) {
    document.getElementById("confirmModalTitle").textContent = title;
    document.getElementById("confirmModalMessage").textContent = message;
    confirmActionCallback = onConfirm;
    document.getElementById("confirmModal").classList.remove("hidden");
}

function closeConfirmModal(confirmed) {
    document.getElementById("confirmModal").classList.add("hidden");
    if (confirmed && typeof confirmActionCallback === "function") {
        confirmActionCallback();
    }
    confirmActionCallback = null;
}

function showToast(message, type = "info") {
    const container = document.getElementById("toastContainer");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    
    let icon = "ℹ️";
    if (type === "success") icon = "✓";
    if (type === "error") icon = "✕";
    if (type === "warning") icon = "⚠️";

    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(40px)";
        toast.style.transition = "all 0.3s ease";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
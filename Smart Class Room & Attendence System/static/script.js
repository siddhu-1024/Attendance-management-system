let students = [];
let attendance = {};


// ---------- LOAD STUDENTS ----------

async function loadStudents() {

    const response = await fetch(
        "/api/students"
    );

    students = await response.json();

    showStudents();
}


// ---------- SHOW STUDENTS ----------

function showStudents(list = students) {

    const table =
        document.getElementById(
            "studentTable"
        );

    table.innerHTML = "";

    list.forEach(student => {

        const status =
            attendance[student.roll_no]
            || "Present";

        attendance[student.roll_no] =
            status;

        const row =
            document.createElement("tr");

        row.innerHTML = `
            <td>${student.roll_no}</td>

            <td>${student.name}</td>

            <td>
                <button
                    class="status-btn
                    ${status === "Present"
                        ? "present"
                        : "absent"}"
                    onclick="changeStatus(
                        '${student.roll_no}'
                    )">

                    ${status}

                </button>
            </td>
        `;

        table.appendChild(row);
    });
}


// ---------- CHANGE STATUS ----------

function changeStatus(rollNo) {

    if (
        attendance[rollNo]
        === "Present"
    ) {

        attendance[rollNo] =
            "Absent";

    } else {

        attendance[rollNo] =
            "Present";
    }

    showStudents();
}


// ---------- SAVE ATTENDANCE ----------

async function saveAttendance() {

    const response = await fetch(
        "/api/attendance/bulk",
        {
            method: "POST",

            headers: {
                "Content-Type":
                    "application/json"
            },

            body: JSON.stringify({
                records: attendance
            })
        }
    );

    const result =
        await response.json();

    if (result.success) {

        alert(
            "Attendance saved successfully!"
        );

        loadDashboard();
        loadLowAttendance();
    }
}


// ---------- SEARCH ----------

function searchStudents() {

    const search =
        document.getElementById(
            "search"
        ).value.toLowerCase();

    const filtered =
        students.filter(student => {

            return (
                student.name
                    .toLowerCase()
                    .includes(search)

                ||

                student.roll_no
                    .toLowerCase()
                    .includes(search)
            );
        });

    showStudents(filtered);
}


// ---------- DASHBOARD ----------

async function loadDashboard() {

    const response = await fetch(
        "/api/dashboard"
    );

    const data =
        await response.json();

    document.getElementById(
        "totalStudents"
    ).textContent = data.students;

    document.getElementById(
        "presentCount"
    ).textContent = data.present;

    document.getElementById(
        "absentCount"
    ).textContent = data.absent;

    document.getElementById(
        "attendancePercent"
    ).textContent =
        data.percentage + "%";
}


// ---------- LOW ATTENDANCE ----------

async function loadLowAttendance() {

    const response = await fetch(
        "/api/attendance/low"
    );

    const students =
        await response.json();

    const box =
        document.getElementById(
            "lowStudents"
        );

    box.innerHTML = "";

    if (students.length === 0) {

        box.innerHTML =
            "<p>No low attendance students.</p>";

        return;
    }

    students.forEach(student => {

        const div =
            document.createElement("div");

        div.className =
            "low-student";

        div.innerHTML = `
            <strong>
                ${student.name}
            </strong>

            <br>

            ${student.roll_no}

            -

            ${student.percentage}%
        `;

        box.appendChild(div);
    });
}


// ---------- START ----------

loadStudents();
loadDashboard();
loadLowAttendance();
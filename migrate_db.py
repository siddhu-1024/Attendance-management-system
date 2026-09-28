import sqlite3
import os

def run_migration():
    db_path = os.path.join(os.path.dirname(__file__), 'instance', 'smart_classroom.db')
    if not os.path.exists(db_path):
        print("Database does not exist yet.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(student)")
    cols = [row[1] for row in cur.fetchall()]

    new_cols = [
        ("department", "VARCHAR(50) DEFAULT 'CAI'"),
        ("section", "VARCHAR(50) DEFAULT 'CAI-A'"),
        ("email", "VARCHAR(120)"),
        ("password_hash", "VARCHAR(255)"),
        ("is_active", "BOOLEAN DEFAULT 1"),
        ("created_at", "DATETIME")
    ]

    for col_name, col_def in new_cols:
        if col_name not in cols:
            print(f"Adding column {col_name} to student table...")
            cur.execute(f"ALTER TABLE student ADD COLUMN {col_name} {col_def}")

    conn.commit()
    conn.close()
    print("Database migration completed.")

if __name__ == "__main__":
    run_migration()


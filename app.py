from flask import Flask, render_template, request, redirect, session
from flask import send_from_directory
import sqlite3
import os
from dotenv import load_dotenv
from google import genai

import random
import smtplib
from email.message import EmailMessage

from werkzeug.security import generate_password_hash, check_password_hash

import shutil
from zipfile import ZipFile


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=GEMINI_API_KEY
)

app = Flask(__name__)



app.secret_key = os.getenv("SECRET_KEY")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
BASE_URL = os.getenv("BASE_URL")
UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx"}

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


# ---------------- HOME ----------------

@app.route("/")
def home():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM files
        WHERE status='approved'
        ORDER BY downloads DESC
        LIMIT 5
    """)

    top_files = cursor.fetchall()

    conn.close()

    return render_template(
        "index.html",
        top_files=top_files
    )


# ---------------- NOTES ----------------

@app.route("/notes")
def notes():
    return render_template(
        "notes.html",
        category="notes"
        )


@app.route("/notes/<year>")
def notes_year(year):
    return render_template(
        "notes_year.html",
        year=year,
        category="notes"
    )


@app.route("/notes/<year>/<semester>")
def notes_subjects(year, semester):

    subjects = SUBJECTS.get(year, {}).get(semester, [])

    return render_template(
        "subjects.html",
        year=year,
        semester=semester,
        category="notes",
        subjects=subjects
    )


@app.route("/notes_files/<year>/<semester>/<subject>")
def notes_files(year, semester, subject):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM files
        WHERE category='Notes'
        AND year=?
        AND semester=?
        AND subject=?
                   AND status='approved'
    """, (year, semester, subject))

    files = cursor.fetchall()

    conn.close()

    return render_template(
        "files.html",
        files=files
    )


# ---------------- PYQ ----------------

@app.route("/pyq")
def pyq():
    return render_template(
        "notes.html",
        category="pyq"
    )


@app.route("/pyq/<year>")
def pyq_year(year):
    return render_template(
        "notes_year.html",
        year=year,
        category="pyq"
    )


@app.route("/pyq/<year>/<semester>")
def pyq_subjects(year, semester):

    subjects = SUBJECTS.get(year, {}).get(semester, [])

    return render_template(
        "subjects.html",
        year=year,
        semester=semester,
        category="pyq",
        subjects=subjects
    )


@app.route("/pyq_files/<year>/<semester>/<subject>")
def pyq_files(year, semester, subject):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM files
        WHERE category='PYQ'
        AND year=?
        AND semester=?
        AND subject=?
        AND status='approved'
    """, (year, semester, subject))

    files = cursor.fetchall()

    conn.close()

    return render_template(
        "files.html",
        files=files
    )


# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        year = request.form["year"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO users
            (name,email,password,year)
            VALUES(?,?,?,?)
        """, (name, email, password, year))

        conn.commit()

        try:
            send_admin_new_student_email(
                name,
                email,
                year
            )
            print("Admin mail sent")
        except Exception as e:
            print("Admin mail error:", e)

        try:
            send_student_welcome_email(
                name,
                email
            )   
            print("Student welcome mail sent to:", email)
        except Exception as e:
            print("Student welcome mail error:", e)

        conn.close()

        return redirect("/profile")

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM users
            WHERE email=?
        """, (email,))

        user = cursor.fetchone()

        conn.close()

        if user and check_password_hash(user[3], password):

            session["user"] = user[1]
            session["user_id"] = user[0]
            session["role"] = user[5]
            
            if user[5] == "admin":
                return redirect("/admin")
            else:
                return redirect("/profile")

    return render_template("login.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")
    
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
                   SELECT *
                   FROM files
                   WHERE user_id=?
                   """, (session["user_id"],))
    
    my_files = cursor.fetchall()
    print(my_files)

    conn.close()

    return render_template(
        "dashboard.html",
        user=session["user"],
        my_files=my_files
    )


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ---------------- UPLOAD PAGE ----------------

@app.route("/upload")
def upload_page():
    return render_template("upload.html")


# ---------------- UPLOAD FILE ----------------

@app.route("/upload", methods=["POST"])
def upload():

    print("FROM DATA:")
    print(request.form)
    print("FROM FILES:")
    print(request.files)

    file = request.files["file"]

    category = request.form["category"]
    year = request.form["year"]
    semester = request.form["semester"]
    subject = request.form["subject"]

    exam_year = request.form.get("exam_year")

    print("YEAR =", year)
    print("SEMESTER =", semester)
    print("SUBJECT =", subject)

    if file:

        if not allowed_file(file.filename):
            return "Only PDF DOCX and PPTX files are allowed"

        filename = file.filename

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM files
            WHERE filename=?
            AND category=?
            AND year=?
            AND semester=?
            AND subject=?
        """, (
            filename,
            category,
            year,
            semester,
            subject
        ))

        existing_file = cursor.fetchone()

        if existing_file:
            conn.close()
            return "This file already exists"

        file.save(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )
        )

        if session.get("role") == "admin":
            status = "approved"
        else:
            status = "pending"

        cursor.execute("""
            INSERT INTO files
            (filename,category,year,semester,subject,status,user_id,exam_year)
            VALUES(?,?,?,?,?,?,?,?)
        """, (
            filename,
            category,
            year,
            semester,
            subject,
            status,
            session["user_id"],
            exam_year
        ))

        file_id = cursor.lastrowid

        conn.commit()

        if session.get("role") !="admin":
            send_admin_upload_email(
                session["user"],
                filename,
                category,
                year,
                semester,
                subject,
                file_id
            )

        conn.close()

        return redirect("/profile")

    return "No file selected"


# ---------------- FILES ----------------

@app.route("/files")
def files():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
                   SELECT *
                   FROM files
                   WHERE status='approved'
               """)

    files = cursor.fetchall()

    conn.close()

    return render_template(
        "files.html",
        files=files
    )


# ---------------- DOWNLOAD ----------------

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
                   UPDATE files
                   SET downloads = downloads + 1
                   WHERE filename=?
                   """, (filename,))
    
    conn.commit()
    conn.close()

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=False
    )

@app.route("/download/<path:filename>")
def download_file(filename):

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE files
        SET downloads = downloads + 1
        WHERE filename=?
    """, (filename,))

    conn.commit()
    conn.close()

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename,
        as_attachment=True
    )

@app.route("/approve/<int:file_id>")
def approve_file(file_id):

    if session.get("role") != "admin":
        return "Access Denied"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    # file details घ्या
    cursor.execute("""
        SELECT *
        FROM files
        WHERE id=?
    """, (file_id,))

    file = cursor.fetchone()

    if file:

        filename = file[1]
        user_id = file[7]

        # student email घ्या
        cursor.execute("""
            SELECT email
            FROM users
            WHERE id=?
        """, (user_id,))

        user = cursor.fetchone()

        # file approve करा
        cursor.execute("""
            UPDATE files
            SET status='approved'
            WHERE id=?
        """, (file_id,))

        conn.commit()

        # email पाठवा
        if user:
            student_email = user[0]

            send_approval_email(
                student_email,
                filename
            )

    conn.close()

    return redirect("/admin")

# ---------------- ADMIN ----------------

@app.route("/admin")
def admin():

    if session.get("role") != "admin":
        return "Access Denied"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("""
    SELECT *
    FROM files
    WHERE status='pending'
    """)
    pending_files = cursor.fetchall()

    cursor.execute("""
                   SELECT *
                   FROM files
                   WHERE category='Notes'
                   """)
    
    all_notes = cursor.fetchall()

    cursor.execute("""
                   SELECT *
                   FROM files
                   WHERE category='PYQ'
                   """)
    
    all_pyq = cursor.fetchall()

    cursor.execute("""
    SELECT *
    FROM files
    WHERE status='approved'
    """)
    approved_files = cursor.fetchall()

    cursor.execute("""
    SELECT SUM(downloads)
    FROM files
""")
    total_downloads = cursor.fetchone()[0]

    if total_downloads is None:
        total_downloads = 0

    cursor.execute("""
    SELECT *
    FROM files
    WHERE status='approved'
    ORDER BY downloads DESC
    LIMIT 5
""")
    top_downloads = cursor.fetchall()

    cursor.execute("""
    SELECT reports.id,
           files.filename,
           users.name,
           users.email,
           reports.reason,
           reports.status
    FROM reports
    JOIN files ON reports.file_id = files.id
    JOIN users ON reports.user_id = users.id
    ORDER BY reports.id DESC
""")

    reported_files = cursor.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        users=users,
        pending_files=pending_files,
        all_notes=all_notes,
        all_pyq=all_pyq,
        approved_files=approved_files,
        total_downloads=total_downloads,
        top_downloads=top_downloads,
        reported_files=reported_files
    )

@app.route("/search")
def search():

    query = request.args.get("subject")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM files
        WHERE status='approved'
        AND (
            subject LIKE ?
            OR year LIKE ?
            OR semester LIKE ?
            OR category LIKE ?
            OR filename LIKE ?
        )
    """, (
        '%' + query + '%',
        '%' + query + '%',
        '%' + query + '%',
        '%' + query + '%',
        '%' + query + '%'
    ))

    files = cursor.fetchall()

    conn.close()

    return render_template(
        "files.html",
        files=files
    )


@app.route("/fix")
def fix():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE files
        SET semester='sem1'
        WHERE semester='Sem 1'
    """)

    conn.commit()
    conn.close()

    return "Updated Successfully"

SUBJECTS = {
    "FY": {
        "sem1": ["Logic Building with C",
                 "Web Technology",
                 "Computer Network"
                 ],

        "sem2": ["OOP's using C++",
                 "Data Structure",
                 "RDBMS",
                 ]
    },

    "SY": {
        "sem3": ["Java Programming",
                 "Programming with Python",
                 "Software Engineering",
                 ],

        "sem4": [ "Web Development using J2EE",
                  "Operating System",
                  "Software Testing"
                  ]
    },

    "TY": {
        "sem5": [ "Linux",
                  ".Net/ C#",
                  "Python for Data Science"],
                  
        "sem6": ["Cloud Computing"]
    }
}

@app.route("/check")
def check():

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(files)")
    data = cursor.fetchall()

    conn.close()

    return str(data)

@app.route("/profile")
def profile():

    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM users
        WHERE id=?
    """, (session["user_id"],))

    user = cursor.fetchone()

    print(user)

    cursor.execute("""
                   SELECT *
                   FROM files
                   WHERE user_id=?
                   ORDER BY id DESC
                   """, (session["user_id"],))
    
    my_files = cursor.fetchall()

    cursor.execute("""
        SELECT COUNT(*)
        FROM files
        WHERE user_id=?
    """, (session["user_id"],))

    total_uploads = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM files
        WHERE user_id=?
        AND status='pending'
    """, (session["user_id"],))

    pending = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*)
        FROM files
        WHERE user_id=?
        AND status='approved'
    """, (session["user_id"],))

    approved = cursor.fetchone()[0]

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        my_files=my_files,
        total_uploads=total_uploads,
        pending=pending,
        approved=approved
    )

@app.route("/upload_profile_photo", methods=["POST"])
def upload_profile_photo():

    if "user_id" not in session:
        return redirect("/login")

    photo = request.files["photo"]

    if photo:

        filename = photo.filename

        photo.save(
            os.path.join(
                app.config["UPLOAD_FOLDER"],
                filename
            )
        )

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users
            SET profile_photo=?
            WHERE id=?
        """, (
            filename,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

    return redirect("/profile")

@app.route("/settings")
def settings():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("settings.html")

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    if request.method == "POST":

        name = request.form["name"]
        year = request.form["year"]
        roll_no = request.form["roll_no"]
        mobile = request.form["mobile"]

        cursor.execute("""
            UPDATE users
            SET name=?,
                year=?,
                roll_no=?,
                mobile=?
            WHERE id=?
        """, (
            name,
            year,
            roll_no,
            mobile,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect("/profile")

    cursor.execute("""
        SELECT *
        FROM users
        WHERE id=?
    """, (session["user_id"],))

    user = cursor.fetchone()

    conn.close()

    return render_template(
        "edit_profile.html",
        user=user
    )

@app.route("/change_profile_photo", methods=["GET", "POST"])
def change_profile_photo():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        photo = request.files["photo"]

        if photo:

            filename = photo.filename

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE users
                SET profile_photo=?
                WHERE id=?
            """, (
                filename,
                session["user_id"]
            ))

            conn.commit()
            conn.close()

            return redirect("/profile")

    return render_template("change_profile_photo.html")

@app.route("/change_password", methods=["GET", "POST"])
def change_password():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        new_password = generate_password_hash(
            request.form["password"]
        )

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users
            SET password=?
            WHERE id=?
        """, (
            new_password,
            session["user_id"]
        ))

        conn.commit()
        conn.close()

        return redirect("/profile")

    return render_template("change_password.html")

def send_otp_email(to_email, otp):

    msg = EmailMessage()

    msg["Subject"] = "Campus Notes & PYQ Hub - OTP"

    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email

    msg.set_content(f"""
Hello Student,

Your OTP for Password Reset is:

{otp}

Do not share this OTP with anyone.

Campus Notes & PYQ Hub
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


def send_approval_email(to_email, filename):


    login_link = f"{BASE_URL}/login"

    msg = EmailMessage()

    msg["Subject"] = "Your File Has Been Approved"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email

    msg.set_content(f"""
Hello Student,

Your uploaded file has been approved.

File Name:
{filename}

Login here:
{login_link}

Campus Notes & PYQ Hub
""")

    msg.add_alternative(f"""
    <html>
    <body style="font-family:Arial; background:#f4f6f9; padding:20px;">

        <div style="max-width:600px; margin:auto; background:white; padding:25px; border-radius:12px; border:1px solid #ddd;">

            <h2 style="color:#0d6efd;">
                📚 Campus Notes & PYQ Hub
            </h2>

            <h3 style="color:#198754;">
                ✅ Your File Has Been Approved
            </h3>

            <p>
                Hello Student,
            </p>

            <p>
                Your uploaded file has been approved by the admin.
            </p>

            <table style="width:100%; border-collapse:collapse; margin-top:15px;">
                <tr>
                    <td style="padding:8px;"><b>File Name</b></td>
                    <td style="padding:8px;">{filename}</td>
                </tr>
                <tr>
                    <td style="padding:8px;"><b>Status</b></td>
                    <td style="padding:8px; color:#198754;"><b>Approved</b></td>
                </tr>
            </table>

            <div style="margin-top:25px;">

                <a href="{login_link}"
                   style="background:#0d6efd; color:white; padding:12px 20px; text-decoration:none; border-radius:8px; display:inline-block;">
                    Login to View File
                </a>

            </div>

            <p style="margin-top:25px; color:#6c757d;">
                Thank you,<br>
                Campus Notes & PYQ Hub
            </p>

        </div>

    </body>
    </html>
    """, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

def send_admin_upload_email(student_name, filename, category, year, semester, subject, file_id):

    approve_link = f"{BASE_URL}/approve/{file_id}"
    reject_link = f"{BASE_URL}/delete/{file_id}"
    admin_panel_link = f"{BASE_URL}/admin"

    msg = EmailMessage()

    msg["Subject"] = "New File Uploaded For Approval"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ADMIN_EMAIL

    msg.set_content(f"""
                    Hello Admin
New file uploaded for approval.

Student Name: {student_name}
File Name: {filename}
Category: {category}
Year: {year}
Semester: {semester}
Subject: {subject}

Admin Panel:
{admin_panel_link}

Approve:
{approve_link}

Reject:
{reject_link}
""")

    msg.add_alternative(f"""
    <html>
    <body style="font-family:Arial; background:#f4f6f9; padding:20px;">

        <div style="max-width:600px; margin:auto; background:white; padding:25px; border-radius:12px; border:1px solid #ddd;">

            <h2 style="color:#0d6efd;">
                📚 Campus Notes & PYQ Hub
            </h2>

            <h3>
                New File Uploaded For Approval
            </h3>

            <p>
                A student has uploaded a new file and it is waiting for admin approval.
            </p>

            <table style="width:100%; border-collapse:collapse; margin-top:15px;">
                <tr>
                    <td><b>Student Name</b></td>
                    <td>{student_name}</td>
                </tr>
                <tr>
                    <td><b>File Name</b></td>
                    <td>{filename}</td>
                </tr>
                <tr>
                    <td><b>Category</b></td>
                    <td>{category}</td>
                </tr>
                <tr>
                    <td><b>Year</b></td>
                    <td>{year}</td>
                </tr>
                <tr>
                    <td><b>Semester</b></td>
                    <td>{semester}</td>
                </tr>
                <tr>
                    <td><b>Subject</b></td>
                    <td>{subject}</td>
                </tr>
                <tr>
                    <td><b>Status</b></td>
                    <td style="color:#ffc107;"><b>Pending</b></td>
                </tr>
            </table>

            <div style="margin-top:25px;">

                <a href="{admin_panel_link}"
                   style="background:#0d6efd; color:white; padding:12px 18px; text-decoration:none; border-radius:8px; display:inline-block; margin-right:8px;">
                    Open Admin Panel
                </a>

                <a href="{approve_link}"
                   style="background:#198754; color:white; padding:12px 18px; text-decoration:none; border-radius:8px; display:inline-block; margin-right:8px;">
                    Approve
                </a>

                <a href="{reject_link}"
                   style="background:#dc3545; color:white; padding:12px 18px; text-decoration:none; border-radius:8px; display:inline-block;">
                    Reject
                </a>

            </div>

            <p style="margin-top:25px; color:#6c757d;">
                Campus Notes & PYQ Hub
            </p>

        </div>

    </body>
    </html>
    """, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            SELECT *
            FROM users
            WHERE email=?
        """, (email,))

        user = cursor.fetchone()

        conn.close()

        if user:

            otp = str(random.randint(100000, 999999))

            session["reset_email"] = email
            session["reset_otp"] = otp

            send_otp_email(email, otp)

            return redirect("/verify_otp")

    return render_template("forgot_password.html")

@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():

    if request.method == "POST":

        entered_otp = request.form["otp"]

        if entered_otp == session.get("reset_otp"):

            return redirect("/reset_password")

        else:
            return "Invalid OTP"

    return render_template("verify_otp.html")

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():

    if "reset_email" not in session:
        return redirect("/forgot_password")

    if request.method == "POST":

        new_password = generate_password_hash(
            request.form["password"]
        )

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users
            SET password=?
            WHERE email=?
        """, (
            new_password,
            session["reset_email"]
        ))

        conn.commit()
        conn.close()

        session.pop("reset_email", None)
        session.pop("reset_otp", None)

        return redirect("/login")

    return render_template("reset_password.html")

@app.route("/student_delete/<int:file_id>")
def student_delete(file_id):

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM files
        WHERE id=?
        AND user_id=?
        AND status='pending'
    """, (
        file_id,
        session["user_id"]
    ))

    conn.commit()
    conn.close()

    return redirect("/profile")

def send_admin_new_student_email(name, email, year):

    msg = EmailMessage()

    msg["Subject"] = "New Student Registered"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ADMIN_EMAIL

    msg.set_content(f"""
Hello Admin,

A new student has registered on Campus Notes & PYQ Hub.

Student Details:

Name: {name}
Email: {email}
Year: {year}

Please check the admin dashboard for more details.

Campus Notes & PYQ Hub
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)


def send_student_welcome_email(name, email):

    login_link = f"{BASE_URL}/login"

    msg = EmailMessage()

    msg["Subject"] = "Welcome to Campus Notes & PYQ Hub"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = email

    msg.set_content("""
Welcome to Campus Notes & PYQ Hub.

Your email client does not support HTML email.
Please login to your account to access notes and PYQs.
""")

    msg.add_alternative(f"""
<html>
<body style="font-family:Arial,sans-serif;background:#f4f6f9;padding:20px;">

<div style="max-width:650px;margin:auto;background:white;border-radius:15px;overflow:hidden;box-shadow:0 4px 15px rgba(0,0,0,0.1);">

<div style="background:linear-gradient(135deg,#0d6efd,#6610f2);padding:30px;text-align:center;color:white;">

    <h1>📚 Campus Notes & PYQ Hub</h1>
    <p>Welcome to the Academic Community</p>

</div>

<div style="padding:30px;">

    <h2 style="color:#0d6efd;">
        Hello {name},
    </h2>

    <p>
        Thank you for registering on <b>Campus Notes & PYQ Hub</b>.
    </p>

    <p>
        Your account has been created successfully and you can now access study resources shared by students and faculty.
    </p>

    <div style="background:#f8f9fa;padding:20px;border-radius:10px;margin-top:20px;">

        <h3>🎯 What You Can Do</h3>

        <p>📚 Access Notes</p>
        <p>📝 Download PYQs</p>
        <p>📤 Upload Study Material</p>
        <p>🔔 Receive Notifications</p>
        <p>👤 Manage Your Profile</p>

    </div>

    <div style="text-align:center;margin-top:30px;">

        <a href="{login_link}"
           style="background:#0d6efd;color:white;padding:14px 28px;text-decoration:none;border-radius:8px;font-size:16px;font-weight:bold;">

            Login Now

        </a>

    </div>

    <hr style="margin-top:30px;">

    <p style="color:#6c757d;">
        We hope this platform helps you learn, collaborate and achieve academic success.
    </p>

    <p>
        Best Regards,<br>
        <b>Campus Notes & PYQ Hub Team</b><br>
        MGM College of CS & IT
    </p>

</div>

<div style="background:#212529;color:white;text-align:center;padding:15px;">
    © 2026 Campus Notes & PYQ Hub
</div>

</div>

</body>
</html>
""", subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

def allowed_file(filename):

    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):

    if session.get("role") != "admin":
        return "Access Denied"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM users
        WHERE id=?
        AND role!='admin'
    """, (user_id,))

    conn.commit()
    conn.close()

    return redirect("/admin")

@app.route("/report/<int:file_id>", methods=["GET", "POST"])
def report_file(file_id):

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        reason = request.form["reason"]

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports
            (file_id,user_id,reason)
            VALUES(?,?,?)
        """, (
            file_id,
            session["user_id"],
            reason
        ))

        cursor.execute("""
            SELECT filename
            FROM files
            WHERE id=?
        """, (file_id,))

        file = cursor.fetchone()

        cursor.execute("""
            SELECT name, email
            FROM users
            WHERE id=?
        """, (session["user_id"],))

        student = cursor.fetchone()

        conn.commit()
        conn.close()

        if file and student:
            send_admin_report_email(
                student[0],
                student[1],
                file[0],
                reason
            )

        return redirect("/files")

    return render_template(
        "report_file.html",
        file_id=file_id
    )

def send_admin_report_email(student_name, student_email, filename, reason):

    admin_panel_link = f"{BASE_URL}/admin"

    msg = EmailMessage()

    msg["Subject"] = "File Reported by Student"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = ADMIN_EMAIL

    msg.set_content(f"""
Hello Admin,

A student has reported a file.

Student Name: {student_name}
Student Email: {student_email}

Reported File:
{filename}

Reason:
{reason}

Please check the Admin Dashboard.

Admin Panel:
{admin_panel_link}

Campus Notes & PYQ Hub
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

@app.route("/backup")
def backup():

    if session.get("role") != "admin":
        return "Access Denied"

    backup_zip = "campus_hub_backup.zip"

    with ZipFile(backup_zip, "w") as zipf:

        zipf.write("database.db")

        for foldername, subfolders, filenames in os.walk(app.config["UPLOAD_FOLDER"]):

            for filename in filenames:

                filepath = os.path.join(foldername, filename)

                zipf.write(filepath)

    return send_from_directory(
        ".",
        backup_zip,
        as_attachment=True
    )


@app.route("/help_bot", methods=["POST"])
def help_bot():

    question = request.form["question"]

    prompt = f"""
You are Campus Notes & PYQ Hub AI Assistant.
Answer in simple Marathi-English mix.

Help students about:
- Notes
- PYQ
- Upload process
- Subjects
- Login/Register
- Password reset
- Report wrong file
- Academic doubts

Question: {question}
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        answer = response.text

    except Exception as e:
        answer = "AI service temporarily unavailable. Please try again later."

    return {"answer": answer}


@app.route("/delete/<int:file_id>")
def delete_file(file_id):

    if session.get("role") != "admin":
        return "Access Denied"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT filename FROM files WHERE id=?",
        (file_id,)
    )

    file = cursor.fetchone()

    if file:

        filename = file[0]

        filepath = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )

        if os.path.exists(filepath):
            os.remove(filepath)

        cursor.execute(
            "DELETE FROM files WHERE id=?",
            (file_id,)
        )

        conn.commit()

    conn.close()

    return redirect("/admin")

@app.route("/debug")
def debug():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id,category,year,semester,subject,status
        FROM files
    """)

    data = cursor.fetchall()
    conn.close()

    return str(data)


#@app.route("/clear_test_files")
#def clear_test_files():

    if session.get("role") != "admin":
        return "Access Denied"

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("DELETE FROM files")
    cursor.execute("DELETE FROM reports")

    conn.commit()
    conn.close()

    for filename in os.listdir(app.config["UPLOAD_FOLDER"]):
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)

        if os.path.isfile(filepath):
            os.remove(filepath)

    return "All uploaded test files and reports deleted successfully"

@app.route("/ai_chat", methods=["POST"])
def ai_chat():

    question = request.form["question"]

    prompt = f"""
You are Campus Notes & PYQ Hub AI Assistant.

Help students regarding:
- Notes
- PYQs
- Upload process
- Subjects
- Academic doubts
- Website usage

Question:
{question}
"""

    try:

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        answer = response.text

    except Exception as e:
        answer = f"AI Error: {e}"

    return {
        "answer": answer
    }


if __name__ == "__main__":
    app.run(debug=False)


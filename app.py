
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import inspect, text
import os

app = Flask(__name__)

app.secret_key = os.environ.get(
    "CIVICEYE_SECRET_KEY",
    "civiceye-local-development-key"
)

ADMIN_PASSWORD = os.environ.get("CIVICEYE_ADMIN_PASSWORD")

ADMIN_PASSWORD_HASH = (
    generate_password_hash(ADMIN_PASSWORD)
    if ADMIN_PASSWORD
    else None
)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///civiceye.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

db = SQLAlchemy(app)


# -----------------------------
# DATABASE MODEL
# -----------------------------

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(200))
    status = db.Column(db.String(30), default="Pending")

    # GPS coordinates
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)


os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# -----------------------------
# HOMEPAGE
# -----------------------------

@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------
# COMMUNITY REPORTS
# -----------------------------

@app.route("/reports")
def reports():
    all_reports = Report.query.order_by(Report.id.desc()).all()

    # Prepare GPS reports as dictionaries for JavaScript
    map_reports = []

    for report in all_reports:
        if report.latitude is not None and report.longitude is not None:
            map_reports.append({
                "id": report.id,
                "title": report.title,
                "category": report.category,
                "location": report.location,
                "status": report.status,
                "latitude": report.latitude,
                "longitude": report.longitude
            })

    return render_template(
        "reports.html",
        reports=all_reports,
        map_reports=map_reports
    )


# -----------------------------
# INDIVIDUAL REPORT DETAILS
# -----------------------------

@app.route("/report/<int:report_id>")
def report_details(report_id):
    report = Report.query.get_or_404(report_id)
    return render_template("report_details.html", report=report)


# -----------------------------
# ADMIN LOGIN
# -----------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")

        if ADMIN_PASSWORD_HASH and check_password_hash(
            ADMIN_PASSWORD_HASH, password
        ):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))

        flash("Incorrect password. Please try again.")

    return render_template("login.html")


# -----------------------------
# ADMIN LOGOUT
# -----------------------------

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------
# ADMIN DASHBOARD
# -----------------------------

@app.route("/admin")
def admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    all_reports = Report.query.order_by(Report.id.desc()).all()

    total_reports = Report.query.count()
    pending_reports = Report.query.filter_by(status="Pending").count()
    progress_reports = Report.query.filter_by(status="In Progress").count()
    resolved_reports = Report.query.filter_by(status="Resolved").count()

    return render_template(
        "admin.html",
        reports=all_reports,
        total_reports=total_reports,
        pending_reports=pending_reports,
        progress_reports=progress_reports,
        resolved_reports=resolved_reports
    )


# -----------------------------
# UPDATE REPORT STATUS
# -----------------------------

@app.route("/update_status/<int:report_id>", methods=["POST"])
def update_status(report_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    report = Report.query.get_or_404(report_id)

    new_status = request.form.get("status")

    if new_status not in ["Pending", "In Progress", "Resolved"]:
        return "Invalid status", 400

    report.status = new_status
    db.session.commit()

    return redirect(url_for("admin"))


# -----------------------------
# DELETE REPORT
# -----------------------------

@app.route("/delete_report/<int:report_id>", methods=["POST"])
def delete_report(report_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("login"))

    report = Report.query.get_or_404(report_id)

    if report.image:
        image_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            report.image
        )

        if os.path.exists(image_path):
            os.remove(image_path)

    db.session.delete(report)
    db.session.commit()

    return redirect(url_for("admin"))


# -----------------------------
# SUBMIT A NEW REPORT
# -----------------------------

@app.route("/report", methods=["GET", "POST"])
def report():
    if request.method == "POST":

        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()

        if not all([title, category, location, description]):
            return "Please fill in all required fields.", 400

        # Read GPS coordinates
        latitude_value = request.form.get("latitude", "").strip()
        longitude_value = request.form.get("longitude", "").strip()

        latitude = None
        longitude = None

        if bool(latitude_value) != bool(longitude_value):
            return "Both GPS coordinates are required.", 400

        if latitude_value and longitude_value:
            try:
                latitude = float(latitude_value)
                longitude = float(longitude_value)
            except ValueError:
                return "Invalid GPS coordinates.", 400

            if not (-90 <= latitude <= 90):
                return "Latitude is out of range.", 400

            if not (-180 <= longitude <= 180):
                return "Longitude is out of range.", 400

        image_file = request.files.get("image")
        image_name = None

        if image_file and image_file.filename:
            allowed_extensions = {"png", "jpg", "jpeg", "webp"}
            extension = image_file.filename.rsplit(".", 1)[-1].lower()

            if extension not in allowed_extensions:
                return "Only PNG, JPG, JPEG and WEBP images are allowed.", 400

            image_name = secure_filename(image_file.filename)

            if not image_name:
                return "Invalid image filename.", 400

            image_file.save(
                os.path.join(app.config["UPLOAD_FOLDER"], image_name)
            )

        new_report = Report(
            title=title,
            category=category,
            location=location,
            description=description,
            image=image_name,
            latitude=latitude,
            longitude=longitude
        )

        db.session.add(new_report)
        db.session.commit()

        return redirect(url_for("home"))

    return render_template("report.html")


# -----------------------------
# CREATE / UPDATE DATABASE TABLES
# -----------------------------

with app.app_context():
    db.create_all()

    existing_columns = {
        column["name"]
        for column in inspect(db.engine).get_columns("report")
    }

    with db.engine.begin() as connection:

        if "latitude" not in existing_columns:
            connection.execute(
                text("ALTER TABLE report ADD COLUMN latitude FLOAT")
            )

        if "longitude" not in existing_columns:
            connection.execute(
                text("ALTER TABLE report ADD COLUMN longitude FLOAT")
            )


# -----------------------------
# RUN APPLICATION
# -----------------------------

print(app.url_map)

if __name__ == "__main__":
    app.run(debug=True)

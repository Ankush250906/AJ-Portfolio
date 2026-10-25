
import os
import secrets
import time
from functools import wraps
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import (
    generate_password_hash, check_password_hash
)

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

secret_key = os.environ.get("SECRET_KEY")
if not secret_key:
    secret_key_path = DATA_DIR / ".secret_key"
    try:
        secret_key = secret_key_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        generated_secret = secrets.token_hex(32)
        try:
            secret_fd = os.open(
                secret_key_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            with os.fdopen(secret_fd, "w", encoding="utf-8") as secret_file:
                secret_file.write(generated_secret)
            secret_key = generated_secret
        except FileExistsError:
            for _ in range(50):
                secret_key = secret_key_path.read_text(
                    encoding="utf-8"
                ).strip()
                if secret_key:
                    break
                time.sleep(0.02)

    if not secret_key:
        raise RuntimeError(
            f"Unable to read or create the Flask secret key at {secret_key_path}."
        )
    app.logger.warning(
        "SECRET_KEY is not set; using a generated key from DATA_DIR. "
        "Set SECRET_KEY in production for consistent sessions."
    )

app.config["SECRET_KEY"] = secret_key

DATABASE_PATH = DATA_DIR / "portfolio.db"

app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///" + str(DATABASE_PATH)
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024

db = SQLAlchemy(app)

CERTIFICATE_UPLOAD_DIR = DATA_DIR / "uploads" / "certificates"
CERTIFICATE_UPLOAD_PREFIX = "/static/uploads/certificates/"
MAX_CERTIFICATE_SIZE = 5 * 1024 * 1024
RESUME_UPLOAD_DIR = DATA_DIR / "uploads" / "resume"
RESUME_UPLOAD_PATH = RESUME_UPLOAD_DIR / "resume.pdf"
MAX_RESUME_SIZE = 5 * 1024 * 1024


# Contact enquiries
class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)


# Freelancing CRM - Client Database
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    business = db.Column(db.String(150))
    service = db.Column(db.String(150))
    lead_source = db.Column(db.String(100))
    deal_amount = db.Column(db.Float, default=0)
    advance_paid = db.Column(db.Float, default=0)
    status = db.Column(db.String(40), default="New Lead")
    payment_status = db.Column(db.String(40), default="Pending")
    follow_up_date = db.Column(db.String(20))
    notes = db.Column(db.Text)



# Admin account
class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)


class DemoWebsite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    url = db.Column(db.String(2048), nullable=False)


class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    issuer = db.Column(db.String(120), nullable=False)
    year = db.Column(db.String(4))
    url = db.Column(db.String(2048), nullable=False)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in to access the dashboard.", "error")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped_view



from datetime import date


def get_client_payment_summary(clients):
    total_deal = sum(client.deal_amount or 0 for client in clients)
    total_advance = sum(client.advance_paid or 0 for client in clients)
    total_outstanding = sum(
        max(0, (client.deal_amount or 0) - (client.advance_paid or 0))
        for client in clients
    )

    return {
        "total_deal": total_deal,
        "total_advance": total_advance,
        "total_outstanding": total_outstanding,
    }


def get_due_followups(clients):
    today = date.today().isoformat()

    return [
        client for client in clients
        if client.follow_up_date
        and client.follow_up_date <= today
        and client.status not in ("Won", "Lost")
    ]

def update_payment_status(client):
    deal_amount = client.deal_amount or 0
    advance_paid = client.advance_paid or 0

    # Advance is the initial payment.
    # ClientPayment records are additional payments.
    additional_payments = sum(
        payment.amount or 0
        for payment in client.payments
    )

    total_received = advance_paid + additional_payments

    if total_received <= 0:
        client.payment_status = "Pending"
    elif deal_amount > 0 and total_received >= deal_amount:
        client.payment_status = "Paid"
    else:
        client.payment_status = "Partial"

    return total_received


@app.route("/static/uploads/certificates/<path:filename>")
def uploaded_certificate(filename):
    return send_from_directory(CERTIFICATE_UPLOAD_DIR, filename)


@app.route("/static/uploads/resume/<path:filename>")
def uploaded_resume(filename):
    return send_from_directory(RESUME_UPLOAD_DIR, filename)



@app.route("/")
def home():
    demos = DemoWebsite.query.order_by(DemoWebsite.id.desc()).all()
    certificates = Certificate.query.order_by(Certificate.id.desc()).all()
    return render_template(
        "index.html",
        demos=demos,
        certificates=certificates,
        resume_available=RESUME_UPLOAD_PATH.is_file()
    )


@app.route("/contact", methods=["POST"])
def contact():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    subject = request.form.get("subject", "").strip()
    message = request.form.get("message", "").strip()

    if not name or not email or not message:
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("home") + "#contact")

    new_message = ContactMessage(
        name=name,
        email=email,
        subject=subject,
        message=message
    )


    db.session.add(new_message)
    db.session.commit()

    flash("Thank you! Your message has been received.", "success")
    return redirect(url_for("home") + "#contact")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin = Admin.query.filter_by(username=username).first()

        if admin and check_password_hash(admin.password_hash, password):
            session.clear()
            session["admin_id"] = admin.id
            session["admin_username"] = admin.username
            return redirect(url_for("admin_dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("admin_login.html")



@app.route("/admin/clients")
@login_required
def clients():
    all_clients = Client.query.order_by(Client.id.desc()).all()

    payment_summary = get_client_payment_summary(all_clients)
    due_followups = get_due_followups(all_clients)

    return render_template(
        "clients.html",
        clients=all_clients,
        payment_summary=payment_summary,
        due_followups=due_followups
    )



@app.route("/admin/clients/add", methods=["GET", "POST"])
@login_required
def add_client():
    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Client name is required.", "error")
            return redirect(url_for("add_client"))

        try:
            deal_amount = float(request.form.get("deal_amount") or 0)
            advance_paid = float(request.form.get("advance_paid") or 0)

            if deal_amount < 0 or advance_paid < 0:
                raise ValueError("Amounts cannot be negative.")

            if advance_paid > deal_amount:
                flash("Advance cannot exceed the total deal amount.", "error")
                return redirect(url_for("add_client"))

        except ValueError:
            flash("Please enter valid non-negative amounts.", "error")
            return redirect(url_for("add_client"))

        client = Client(
            name=name,
            phone=request.form.get("phone", "").strip(),
            email=request.form.get("email", "").strip(),
            business=request.form.get("business", "").strip(),
            service=request.form.get("service", "").strip(),
            lead_source=request.form.get("lead_source", "").strip(),
            deal_amount=deal_amount,
            advance_paid=advance_paid,
            status=request.form.get("status", "New Lead"),
            payment_status=request.form.get("payment_status", "Pending"),
            follow_up_date=request.form.get("follow_up_date", "").strip(),
            notes=request.form.get("notes", "").strip()
        )

        db.session.add(client)
        db.session.commit()

        flash("Client added successfully!", "success")
        return redirect(url_for("clients"))

    return render_template("add_client.html", client=None)


# Edit an existing client
@app.route("/admin/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def edit_client(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Client name is required.", "error")
            return redirect(url_for("edit_client", client_id=client.id))

        try:
            deal_amount = float(request.form.get("deal_amount") or 0)
            advance_paid = float(request.form.get("advance_paid") or 0)

            if (
                deal_amount < 0
                or advance_paid < 0
                or advance_paid > deal_amount
            ):
                raise ValueError

        except ValueError:
            flash(
                "Enter valid amounts. Advance cannot exceed the deal amount.",
                "error"
            )
            return redirect(url_for("edit_client", client_id=client.id))

        client.name = name
        client.phone = request.form.get("phone", "").strip()
        client.email = request.form.get("email", "").strip()
        client.business = request.form.get("business", "").strip()
        client.service = request.form.get("service", "").strip()
        client.lead_source = request.form.get("lead_source", "").strip()
        client.deal_amount = deal_amount
        client.advance_paid = advance_paid
        client.status = request.form.get("status", "New Lead")
        client.payment_status = request.form.get(
            "payment_status", "Pending"
        )
        client.follow_up_date = request.form.get(
            "follow_up_date", ""
        ).strip()
        client.notes = request.form.get("notes", "").strip()

        db.session.commit()

        flash("Client updated successfully!", "success")
        return redirect(url_for("clients"))

    return render_template("edit_client.html", client=client)


# Delete an existing client
@app.route("/admin/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def delete_client(client_id):
    client = db.get_or_404(Client, client_id)

    db.session.delete(client)
    db.session.commit()

    flash("Client deleted successfully.", "success")
    return redirect(url_for("clients"))




@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    enquiries = ContactMessage.query.order_by(
        ContactMessage.id.desc()
    ).all()
    demos = DemoWebsite.query.order_by(DemoWebsite.id.desc()).all()
    certificates = Certificate.query.order_by(Certificate.id.desc()).all()

    return render_template(
        "admin_dashboard.html",
        enquiries=enquiries,
        total_enquiries=len(enquiries),
        demos=demos,
        certificates=certificates,
        resume_available=RESUME_UPLOAD_PATH.is_file()
    )


@app.route("/admin/demos/add", methods=["POST"])
@login_required
def add_demo():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    url = request.form.get("url", "").strip()

    try:
        parsed_url = urlsplit(url)
        valid_url = parsed_url.scheme in ("http", "https") and parsed_url.netloc
    except ValueError:
        valid_url = False

    if not title or not description or not valid_url:
        flash("Enter a title, description, and a valid http:// or https:// demo URL.", "error")
        return redirect(url_for("admin_dashboard"))

    if len(title) > 120 or len(description) > 500 or len(url) > 2048:
        flash("Title, description, or URL is too long.", "error")
        return redirect(url_for("admin_dashboard"))

    db.session.add(DemoWebsite(title=title, description=description, url=url))
    db.session.commit()

    flash("Demo website added to your portfolio.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/demos/<int:demo_id>/delete", methods=["POST"])
@login_required
def delete_demo(demo_id):
    demo = db.get_or_404(DemoWebsite, demo_id)
    db.session.delete(demo)
    db.session.commit()

    flash("Demo website removed from your portfolio.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/certificates/add", methods=["POST"])
@login_required
def add_certificate():
    title = request.form.get("title", "").strip()
    issuer = request.form.get("issuer", "").strip()
    year = request.form.get("year", "").strip()
    uploaded_file = request.files.get("image")

    if not title or not issuer or not uploaded_file or not uploaded_file.filename:
        flash("Enter the certificate name and issuer, and choose an image to upload.", "error")
        return redirect(url_for("admin_dashboard"))

    if len(title) > 120 or len(issuer) > 120 or len(year) > 4:
        flash("Certificate details are too long.", "error")
        return redirect(url_for("admin_dashboard"))

    if year and (len(year) != 4 or not year.isdigit()):
        flash("Enter the certificate year using four digits.", "error")
        return redirect(url_for("admin_dashboard"))

    image_data = uploaded_file.stream.read(MAX_CERTIFICATE_SIZE + 1)
    if len(image_data) > MAX_CERTIFICATE_SIZE:
        flash("Certificate images must be 5 MB or smaller.", "error")
        return redirect(url_for("admin_dashboard"))

    image_types = (
        (b"\x89PNG\r\n\x1a\n", "png"),
        (b"\xff\xd8\xff", "jpg"),
        (b"GIF87a", "gif"),
        (b"GIF89a", "gif"),
    )
    extension = next(
        (extension for signature, extension in image_types if image_data.startswith(signature)),
        None
    )
    if extension is None and len(image_data) >= 12:
        if image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP":
            extension = "webp"

    if extension is None:
        flash("Upload a valid JPG, PNG, GIF, or WebP image.", "error")
        return redirect(url_for("admin_dashboard"))

    filename = f"{uuid4().hex}.{extension}"
    CERTIFICATE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_path = CERTIFICATE_UPLOAD_DIR / filename
    image_path.write_bytes(image_data)

    certificate = Certificate(
        title=title,
        issuer=issuer,
        year=year or None,
        url=url_for("static", filename=f"uploads/certificates/{filename}")
    )
    db.session.add(certificate)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        image_path.unlink(missing_ok=True)
        raise

    flash("Certificate added to your portfolio.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/certificates/<int:certificate_id>/delete", methods=["POST"])
@login_required
def delete_certificate(certificate_id):
    certificate = db.get_or_404(Certificate, certificate_id)
    image_path = None
    if certificate.url.startswith(CERTIFICATE_UPLOAD_PREFIX):
        filename = Path(urlsplit(certificate.url).path).name
        candidate_path = CERTIFICATE_UPLOAD_DIR / filename
        if candidate_path.parent.resolve() == CERTIFICATE_UPLOAD_DIR.resolve():
            image_path = candidate_path

    image_data = None
    if image_path and image_path.exists():
        try:
            image_data = image_path.read_bytes()
            image_path.unlink()
        except PermissionError:
            flash("Close the certificate image and try removing it again.", "error")
            return redirect(url_for("admin_dashboard"))

    db.session.delete(certificate)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        if image_data is not None:
            image_path.write_bytes(image_data)
        raise

    flash("Certificate removed from your portfolio.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/resume/upload", methods=["POST"])
@login_required
def upload_resume():
    uploaded_file = request.files.get("resume")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose a PDF resume to upload.", "error")
        return redirect(url_for("admin_dashboard"))

    resume_data = uploaded_file.stream.read(MAX_RESUME_SIZE + 1)
    if len(resume_data) > MAX_RESUME_SIZE:
        flash("Resume PDF must be 5 MB or smaller.", "error")
        return redirect(url_for("admin_dashboard"))

    if not resume_data.startswith(b"%PDF-"):
        flash("Upload a valid PDF file.", "error")
        return redirect(url_for("admin_dashboard"))

    RESUME_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RESUME_UPLOAD_PATH.write_bytes(resume_data)

    flash("Resume uploaded successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/resume/delete", methods=["POST"])
@login_required
def delete_resume():
    if RESUME_UPLOAD_PATH.is_file():
        RESUME_UPLOAD_PATH.unlink()

    flash("Resume removed from your portfolio.", "success")
    return redirect(url_for("admin_dashboard"))


@app.errorhandler(413)
def request_entity_too_large(error):
    if request.endpoint == "add_certificate":
        flash("Certificate images must be 5 MB or smaller.", "error")
        return redirect(url_for("admin_dashboard"))
    if request.endpoint == "upload_resume":
        flash("Resume PDF must be 5 MB or smaller.", "error")
        return redirect(url_for("admin_dashboard"))
    return "Request too large.", 413


@app.route("/admin/logout", methods=["POST"])
@login_required
def admin_logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin_login"))


# Individual payments received from clients
class ClientPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(
        db.Integer,
        db.ForeignKey("client.id"),
        nullable=False
    )
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.String(10), nullable=False)
    method = db.Column(db.String(50), default="Other")
    reference = db.Column(db.String(120))
    notes = db.Column(db.Text)

    client = db.relationship("Client", backref="payments")



# Individual payments received from a client
@app.route("/admin/clients/<int:client_id>/payments", methods=["GET", "POST"])
@login_required
def client_payments(client_id):
    client = db.get_or_404(Client, client_id)

    if request.method == "POST":
        try:
            amount = float(request.form.get("amount") or 0)
            if amount <= 0:
                raise ValueError
        except ValueError:
            flash("Enter a valid payment amount greater than zero.", "error")
            return redirect(url_for("client_payments", client_id=client.id))

        payment_date = request.form.get("payment_date", "").strip()
        if not payment_date:
            payment_date = date.today().isoformat()

        payment = ClientPayment(
            client_id=client.id,
            amount=amount,
            payment_date=payment_date,
            method=request.form.get("method", "Other"),
            reference=request.form.get("reference", "").strip(),
            notes=request.form.get("notes", "").strip()
        )

        
        return redirect(url_for("client_payments", client_id=client.id))

    payments = ClientPayment.query.filter_by(
        client_id=client.id
    ).order_by(ClientPayment.id.desc()).all()

    total_paid = sum(payment.amount for payment in payments)
    outstanding = max(0, (client.deal_amount or 0) - total_paid)

    return render_template(
        "client_payments.html",
        client=client,
        payments=payments,
        total_paid=total_paid,
        outstanding=outstanding,
        today=date.today().isoformat()
    )


with app.app_context():
    db.create_all()

    # Create the first admin only when credentials are provided.
    admin_username = os.environ.get("ADMIN_USERNAME", "").strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")

    if admin_username and admin_password:
        existing_admin = Admin.query.filter_by(
            username=admin_username
        ).first()

        if not existing_admin:
            admin = Admin(
                username=admin_username,
                password_hash=generate_password_hash(admin_password)
            )
            db.session.add(admin)
            db.session.commit()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")

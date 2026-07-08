from functools import wraps
from datetime import datetime, date

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import String, cast, func, or_
from werkzeug.local import LocalProxy

from model import Booking, Trek, User, db

app = Flask(__name__)
app.config["SECRET_KEY"] = "trekking-management-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///trekking.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

ADMIN_ID = "admin"
ADMIN_PASSWORD = "admin123"


class AnonymousUser:
    is_authenticated = False
    is_approved = False
    role = None
    status = "active"
    id = None
    name = "Guest"
    email = ""
    phone = ""


class AdminUser:
    is_authenticated = True
    is_approved = True
    role = "admin"
    status = "active"
    id = ADMIN_ID
    name = "Admin"
    email = "admin@local"
    phone = ""


def _get_current_user():
    return getattr(g, "current_user", AnonymousUser())


current_user = LocalProxy(_get_current_user)


def login_user(user):
    if getattr(user, "role", None) == "admin":
        session["auth_role"] = "admin"
        session["user_id"] = ADMIN_ID
        return

    session["auth_role"] = user.role
    session["user_id"] = user.id


def logout_user():
    session.pop("user_id", None)
    session.pop("auth_role", None)


@app.before_request
def load_current_user():
    if session.get("auth_role") == "admin":
        g.current_user = AdminUser()
        return

    user_id = session.get("user_id")
    if not user_id:
        g.current_user = AnonymousUser()
        return

    user = db.session.get(User, int(user_id))
    if not user:
        session.pop("user_id", None)
        session.pop("auth_role", None)
        g.current_user = AnonymousUser()
        return

    g.current_user = user


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("login"))
            if current_user.status == "blacklisted":
                logout_user()
                flash("Your account has been blacklisted.", "danger")
                return redirect(url_for("login"))
            if current_user.role == "staff" and not current_user.is_approved:
                logout_user()
                flash("Your staff account is waiting for admin approval.", "warning")
                return redirect(url_for("login"))
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def trek_participant_count(trek_id):
    return db.session.query(func.count(Booking.id)).filter(
        Booking.trek_id == trek_id,
        Booking.status == "Booked",
    ).scalar() or 0


def trek_to_dict(trek):
    return {
        "id": trek.id,
        "trek_name": trek.trek_name,
        "location": trek.location,
        "difficulty": trek.difficulty,
        "duration_days": trek.duration_days,
        "total_slots": trek.total_slots,
        "available_slots": trek.available_slots,
        "status": trek.status,
        "assigned_staff": trek.assigned_staff.name if trek.assigned_staff else None,
        "participant_count": trek_participant_count(trek.id),
        "start_date": trek.start_date.isoformat() if trek.start_date else None,
        "end_date": trek.end_date.isoformat() if trek.end_date else None,
    }


def booking_to_dict(booking):
    return {
        "id": booking.id,
        "user_id": booking.user_id,
        "user_name": booking.user.name,
        "trek_id": booking.trek_id,
        "trek_name": booking.trek.trek_name,
        "status": booking.status,
        "booking_date": booking.booking_date.isoformat(),
    }


def api_error(message, status_code):
    return jsonify({"error": message}), status_code


def api_auth_required(*roles):
    if not current_user.is_authenticated:
        return api_error("Authentication required.", 401)
    if current_user.status == "blacklisted":
        return api_error("This account is blacklisted.", 403)
    if current_user.role == "staff" and not current_user.is_approved:
        return api_error("Staff account is awaiting admin approval.", 403)
    if roles and current_user.role not in roles:
        return api_error("Forbidden.", 403)
    return None


@app.context_processor
def inject_globals():
    return {
        "date_today": date.today(),
        "current_user": current_user,
    }


@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", request.form.get("email", "")).strip().lower()
        password = request.form.get("password", "")

        if identifier == ADMIN_ID and password == ADMIN_PASSWORD:
            login_user(AdminUser())
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))

        user = User.query.filter(func.lower(User.email) == identifier).first()

        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        if user.status == "blacklisted":
            flash("This account is blacklisted.", "danger")
            return render_template("login.html")

        if user.role == "staff" and not user.is_approved:
            flash("Your staff account is awaiting admin approval.", "warning")
            return render_template("login.html")

        login_user(user)
        flash("Logged in successfully.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in {"user", "staff"}:
        abort(404)

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Name, email, and password are required.", "danger")
            return render_template("register.html", role=role)

        existing = User.query.filter(func.lower(User.email) == email).first()
        if existing:
            flash("An account with this email already exists.", "danger")
            return render_template("register.html", role=role)

        user = User(
            name=name,
            email=email,
            phone=phone,
            role=role,
            status="active" if role == "user" else "pending",
            is_approved=role == "user",
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash(
            "Registration successful. Your staff account is waiting for approval." if role == "staff" else "Registration successful. You can now log in.",
            "success",
        )
        return redirect(url_for("login"))

    return render_template("register.html", role=role)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if current_user.role == "staff":
        return redirect(url_for("staff_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    trek_count = Trek.query.count()
    user_count = User.query.filter_by(role="user").count()
    staff_count = User.query.filter_by(role="staff").count()
    booking_count = Booking.query.count()
    pending_staff = User.query.filter_by(role="staff", is_approved=False).order_by(User.created_at.desc()).all()
    recent_bookings = Booking.query.order_by(Booking.booking_date.desc()).limit(5).all()
    return render_template(
        "admin_dashboard.html",
        trek_count=trek_count,
        user_count=user_count,
        staff_count=staff_count,
        booking_count=booking_count,
        pending_staff=pending_staff,
        recent_bookings=recent_bookings,
    )


@app.route("/admin/treks", methods=["GET", "POST"])
@role_required("admin")
def admin_treks():
    if request.method == "POST":
        trek = Trek(
            trek_name=request.form.get("trek_name", "").strip(),
            location=request.form.get("location", "").strip(),
            difficulty=request.form.get("difficulty", "Easy"),
            duration_days=int(request.form.get("duration_days", 1)),
            total_slots=int(request.form.get("total_slots", 1)),
            available_slots=int(request.form.get("available_slots", request.form.get("total_slots", 1))),
            description=request.form.get("description", "").strip(),
            start_date=parse_date(request.form.get("start_date")),
            end_date=parse_date(request.form.get("end_date")),
            status=request.form.get("status", "Pending"),
            assigned_staff_id=int(request.form.get("assigned_staff_id")) if request.form.get("assigned_staff_id") else None,
        )
        if trek.available_slots > trek.total_slots:
            trek.available_slots = trek.total_slots
        db.session.add(trek)
        db.session.commit()
        flash("Trek created successfully.", "success")
        return redirect(url_for("admin_treks"))

    treks = Trek.query.order_by(Trek.created_at.desc()).all()
    staff_members = User.query.filter_by(role="staff", is_approved=True, status="active").order_by(User.name.asc()).all()
    return render_template("admin_treks.html", treks=treks, staff_members=staff_members)


@app.route("/admin/treks/<int:trek_id>/edit", methods=["GET", "POST"])
@role_required("admin")
def admin_edit_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    staff_members = User.query.filter_by(role="staff", is_approved=True, status="active").order_by(User.name.asc()).all()

    if request.method == "POST":
        trek.trek_name = request.form.get("trek_name", "").strip()
        trek.location = request.form.get("location", "").strip()
        trek.difficulty = request.form.get("difficulty", "Easy")
        trek.duration_days = int(request.form.get("duration_days", 1))
        trek.total_slots = int(request.form.get("total_slots", 1))
        trek.available_slots = min(int(request.form.get("available_slots", 1)), trek.total_slots)
        trek.description = request.form.get("description", "").strip()
        trek.start_date = parse_date(request.form.get("start_date"))
        trek.end_date = parse_date(request.form.get("end_date"))
        trek.status = request.form.get("status", trek.status)
        trek.assigned_staff_id = int(request.form.get("assigned_staff_id")) if request.form.get("assigned_staff_id") else None
        db.session.commit()
        flash("Trek updated successfully.", "success")
        return redirect(url_for("admin_treks"))

    return render_template("trek_form.html", trek=trek, staff_members=staff_members, mode="admin")


@app.route("/admin/treks/<int:trek_id>/delete", methods=["POST"])
@role_required("admin")
def admin_delete_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    db.session.delete(trek)
    db.session.commit()
    flash("Trek deleted successfully.", "info")
    return redirect(url_for("admin_treks"))


@app.route("/admin/staff", methods=["GET", "POST"])
@role_required("admin")
def admin_staff():
    if request.method == "POST":
        staff_id = int(request.form.get("staff_id"))
        action = request.form.get("action")
        staff = User.query.get_or_404(staff_id)
        if staff.role != "staff":
            abort(400)
        if action == "approve":
            staff.is_approved = True
            staff.status = "active"
        elif action == "blacklist":
            staff.status = "blacklisted"
        elif action == "unblacklist":
            staff.status = "active"
        db.session.commit()
        flash("Staff status updated.", "success")
        return redirect(url_for("admin_staff"))

    staff_members = User.query.filter_by(role="staff").order_by(User.created_at.desc()).all()
    return render_template("admin_staff.html", staff_members=staff_members)


@app.route("/admin/users", methods=["GET", "POST"])
@role_required("admin")
def admin_users():
    if request.method == "POST":
        user_id = int(request.form.get("user_id"))
        action = request.form.get("action")
        user = User.query.get_or_404(user_id)
        if user.role != "user":
            abort(400)
        if action == "blacklist":
            user.status = "blacklisted"
        elif action == "unblacklist":
            user.status = "active"
        db.session.commit()
        flash("User status updated.", "success")
        return redirect(url_for("admin_users"))

    users = User.query.filter_by(role="user").order_by(User.created_at.desc()).all()
    return render_template("admin_users.html", users=users)


@app.route("/admin/bookings")
@role_required("admin")
def admin_bookings():
    bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
    return render_template("admin_bookings.html", bookings=bookings)


@app.route("/admin/search")
@role_required("admin")
def admin_search():
    query_text = request.args.get("q", "").strip()
    scope = request.args.get("scope", "all")
    treks = users = staff_members = []

    if query_text:
        pattern = f"%{query_text.lower()}%"
        if scope in {"all", "treks"}:
            treks = Trek.query.filter(
                or_(
                    func.lower(Trek.trek_name).like(pattern),
                    func.lower(Trek.location).like(pattern),
                    cast(Trek.id, String).like(pattern),
                )
            ).all()
        if scope in {"all", "users"}:
            users = User.query.filter(
                User.role == "user",
                or_(
                    func.lower(User.name).like(pattern),
                    func.lower(User.email).like(pattern),
                    cast(User.id, String).like(pattern),
                )
            ).all()
        if scope in {"all", "staff"}:
            staff_members = User.query.filter(
                User.role == "staff",
                or_(
                    func.lower(User.name).like(pattern),
                    func.lower(User.email).like(pattern),
                    cast(User.id, String).like(pattern),
                )
            ).all()

    return render_template("admin_search.html", query_text=query_text, scope=scope, treks=treks, users=users, staff_members=staff_members)


@app.route("/staff")
@role_required("staff")
def staff_dashboard():
    assigned_treks = Trek.query.filter_by(assigned_staff_id=current_user.id).order_by(Trek.start_date.asc().nullslast()).all()
    trek_counts = {trek.id: trek_participant_count(trek.id) for trek in assigned_treks}
    return render_template("staff_dashboard.html", assigned_treks=assigned_treks, trek_counts=trek_counts)


@app.route("/staff/trek/<int:trek_id>/manage", methods=["GET", "POST"])
@role_required("staff")
def staff_manage_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.assigned_staff_id != current_user.id:
        abort(403)

    if request.method == "POST":
        trek.available_slots = min(int(request.form.get("available_slots", trek.available_slots)), trek.total_slots)
        trek.status = request.form.get("status", trek.status)
        if trek.status == "Completed":
            for booking in trek.bookings:
                if booking.status == "Booked":
                    booking.status = "Completed"
        db.session.commit()
        flash("Trek updated successfully.", "success")
        return redirect(url_for("staff_dashboard"))

    participants = Booking.query.filter_by(trek_id=trek.id).order_by(Booking.booking_date.desc()).all()
    return render_template("staff_manage_trek.html", trek=trek, participants=participants)


@app.route("/staff/trek/<int:trek_id>/participants")
@role_required("staff")
def staff_participants(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.assigned_staff_id != current_user.id:
        abort(403)
    participants = Booking.query.filter_by(trek_id=trek.id).order_by(Booking.booking_date.desc()).all()
    return render_template("staff_participants.html", trek=trek, participants=participants)


@app.route("/user")
@role_required("user")
def user_dashboard():
    difficulty = request.args.get("difficulty", "").strip()
    location = request.args.get("location", "").strip()
    trek_query = Trek.query.filter(Trek.status == "Open")
    if difficulty:
        trek_query = trek_query.filter(Trek.difficulty == difficulty)
    if location:
        trek_query = trek_query.filter(func.lower(Trek.location).like(f"%{location.lower()}%"))

    available_treks = trek_query.order_by(Trek.start_date.asc().nullslast()).all()
    booked_treks = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    return render_template(
        "user_dashboard.html",
        available_treks=available_treks,
        booked_treks=booked_treks,
        difficulty=difficulty,
        location=location,
    )


@app.route("/treks/<int:trek_id>")
@login_required
def trek_detail(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    booking = Booking.query.filter_by(user_id=current_user.id, trek_id=trek.id).first() if current_user.role == "user" else None
    return render_template("trek_detail.html", trek=trek, booking=booking)


@app.route("/treks/<int:trek_id>/book", methods=["POST"])
@role_required("user")
def book_trek(trek_id):
    trek = Trek.query.get_or_404(trek_id)
    if trek.status != "Open":
        flash("This trek is not open for booking.", "danger")
        return redirect(url_for("user_dashboard"))
    if trek.available_slots <= 0:
        flash("No slots are available for this trek.", "danger")
        return redirect(url_for("user_dashboard"))

    existing = Booking.query.filter_by(user_id=current_user.id, trek_id=trek.id).first()
    if existing and existing.status == "Booked":
        flash("You already have an active booking for this trek.", "warning")
        return redirect(url_for("user_dashboard"))

    if existing and existing.status in {"Completed", "Cancelled"}:
        flash("A history entry already exists for this trek.", "warning")
        return redirect(url_for("user_dashboard"))

    booking = Booking(user_id=current_user.id, trek_id=trek.id, status="Booked")
    trek.available_slots -= 1
    db.session.add(booking)
    db.session.commit()
    flash("Trek booked successfully.", "success")
    return redirect(url_for("user_dashboard"))


@app.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@role_required("user")
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        abort(403)
    if booking.status != "Booked":
        flash("Only active bookings can be cancelled.", "warning")
        return redirect(url_for("user_dashboard"))
    booking.status = "Cancelled"
    booking.trek.available_slots += 1
    db.session.commit()
    flash("Booking cancelled.", "info")
    return redirect(url_for("user_dashboard"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", current_user.name).strip()
        current_user.phone = request.form.get("phone", current_user.phone)
        if request.form.get("password"):
            current_user.set_password(request.form.get("password"))
        db.session.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile"))
    return render_template("profile.html")


@app.route("/history")
@role_required("user")
def history():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
    return render_template("history.html", bookings=bookings)


@app.route("/api/treks", methods=["GET"])
def api_treks():
    treks = Trek.query.order_by(Trek.id.asc()).all()
    return jsonify([trek_to_dict(trek) for trek in treks])


@app.route("/api/treks/<int:trek_id>", methods=["GET", "PUT"])
def api_trek_detail(trek_id):
    trek = Trek.query.get_or_404(trek_id)

    if request.method == "GET":
        return jsonify(trek_to_dict(trek))

    auth_error = api_auth_required("admin", "staff")
    if auth_error:
        return auth_error
    if current_user.role == "staff" and trek.assigned_staff_id != current_user.id:
        return api_error("You can only update your assigned trek.", 403)

    payload = request.get_json(silent=True) or {}
    allowed_statuses = {"Pending", "Approved", "Open", "Closed", "Ongoing", "Completed"}

    if "available_slots" in payload:
        try:
            available_slots = int(payload["available_slots"])
        except (TypeError, ValueError):
            return api_error("available_slots must be an integer.", 400)
        if available_slots < 0 or available_slots > trek.total_slots:
            return api_error("available_slots must be between 0 and total_slots.", 400)
        trek.available_slots = available_slots

    if "status" in payload:
        status = str(payload["status"]).strip()
        if status not in allowed_statuses:
            return api_error("Invalid trek status.", 400)
        trek.status = status
        if status == "Completed":
            for booking in trek.bookings:
                if booking.status == "Booked":
                    booking.status = "Completed"

    db.session.commit()
    return jsonify(trek_to_dict(trek))


@app.route("/api/bookings", methods=["GET", "POST"])
def api_bookings():
    auth_error = api_auth_required("admin", "staff", "user")
    if auth_error:
        return auth_error

    if request.method == "GET":
        if current_user.role == "admin":
            bookings = Booking.query.order_by(Booking.booking_date.desc()).all()
        elif current_user.role == "staff":
            assigned_trek_ids = [trek.id for trek in Trek.query.filter_by(assigned_staff_id=current_user.id).all()]
            bookings = Booking.query.filter(Booking.trek_id.in_(assigned_trek_ids)).order_by(Booking.booking_date.desc()).all()
        else:
            bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.booking_date.desc()).all()
        return jsonify([booking_to_dict(booking) for booking in bookings])

    if current_user.role != "user":
        return api_error("Only trekkers can create bookings through the API.", 403)

    payload = request.get_json(silent=True) or {}
    trek_id = payload.get("trek_id")
    if trek_id is None:
        return api_error("trek_id is required.", 400)

    trek = Trek.query.get(trek_id)
    if not trek:
        return api_error("Trek not found.", 404)
    if trek.status != "Open":
        return api_error("This trek is not open for booking.", 400)
    if trek.available_slots <= 0:
        return api_error("No slots are available for this trek.", 400)

    existing = Booking.query.filter_by(user_id=current_user.id, trek_id=trek.id).first()
    if existing and existing.status in {"Booked", "Completed"}:
        return api_error("You already have a booking for this trek.", 400)
    if existing and existing.status in {"Completed", "Cancelled"}:
        return api_error("A history entry already exists for this trek.", 400)

    booking = Booking(user_id=current_user.id, trek_id=trek.id, status="Booked")
    trek.available_slots -= 1
    db.session.add(booking)
    db.session.commit()
    return jsonify(booking_to_dict(booking)), 201


@app.route("/api/bookings/<int:booking_id>", methods=["GET", "DELETE"])
def api_booking_detail(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    auth_error = api_auth_required("admin", "staff", "user")
    if auth_error:
        return auth_error

    if current_user.role == "staff" and booking.trek.assigned_staff_id != current_user.id:
        return api_error("You can only access bookings for your assigned treks.", 403)
    if current_user.role == "user" and booking.user_id != current_user.id:
        return api_error("You can only access your own bookings.", 403)

    if request.method == "GET":
        return jsonify(booking_to_dict(booking))

    if booking.status != "Booked":
        return api_error("Only active bookings can be cancelled.", 400)

    booking.status = "Cancelled"
    booking.trek.available_slots += 1
    db.session.commit()
    return jsonify(booking_to_dict(booking))


@app.route("/initialize")
def initialize_database():
    db.create_all()
    flash("Database initialized.", "success")
    return redirect(url_for("login"))


@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", title="Access denied", message="You do not have permission to access this page."), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", title="Page not found", message="The requested page could not be found."), 404


with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)

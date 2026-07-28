import os

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for
)

from db.database import AUTH, Session


app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "FLASK_SECRET_KEY",
    "super_secret_string_that_must_be_kept_secret_65762948379286418994091"  #change this and keep it private
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

def get_database_session():
    if "database_session" not in g:
        g.database_session = Session(AUTH)

        if "username" in session:
            g.database_session.uname = {
                "username": session["username"]
            }

    return g.database_session

def credentials_are_valid(username, password):
    test_session = Session((username, password))

    try:
        test_session._executeQuery("RETURN 1")
        return True
    except Exception:
        return False
    finally:
        test_session.driver.close()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/search")
def search_results():
    search_term = request.args.get("q", "").strip()
    doctors = []

    if search_term:
        database = get_database_session()

        database_results = database.searchDoctors(
            search_term
        )

        for result in database_results:
            doctor_data = result.get("doctor")

            if doctor_data is None:
                continue

            # Make a separate dictionary for the template.
            doctor = dict(doctor_data)

            doctor["hospital"] = result.get("hospital")
            doctor["average_rating"] = (
                result.get("average_rating") or 0
            )
            doctor["review_count"] = (
                result.get("review_count") or 0
            )

            doctors.append(doctor)

    return render_template(
        "search_results.html",
        search_term=search_term,
        doctors=doctors
    )


@app.get("/doctor/<doctor_uuid>")
def doctor_profile(doctor_uuid):
    database = get_database_session()
    profile =database.getDoctorProfile(
        doctor_uuid
    )

    current_doctor = database.getLinkedDoctorProfile(session["username"]) if "username" in session else None
    is_own_profile = current_doctor is not None and current_doctor["doctor"]["uuid"] == doctor_uuid

    verified = database.isDoctorVerified({'uuid': doctor_uuid})

    if profile is None:
        abort(404)

    doctor = dict(profile["doctor"])

    # This must use profile.get(), not dict.get().
    reviews = profile.get("reviews", [])

    reviews.sort(
        key=lambda review: review.get("date", ""),
        reverse=True
    )

    for review in reviews:
        review["comments"] = database.getComments(
            review["uuid"]
        )

    doctor["average_rating"] = (
        profile.get("average_rating") or 0
    )

    doctor["review_count"] = len(reviews)

    return render_template(
        "doctor_profile.html",
        doctor=doctor,
        hospital=profile.get("hospital"),
        reviews=reviews,
        is_own_profile=is_own_profile,
        verified=verified
    )

@app.route("/login", methods = ["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("login.html")

        if not credentials_are_valid(username, password):
            flash("The username or password is incorrect.", "danger")
            return render_template("login.html")

        database = get_database_session()
        role = database.getUserRole(username)

        if role is None:
            flash(
                "The application user account could not be found.",
                "danger"
            )
            return render_template("login.html")

        session["username"] = username
        session["role"] = role

        flash(
            f"Welcome, {username}.",
            "success"
        )

        return redirect(url_for("index"))

    return render_template("login.html")

@app.get("/logout")
def logout():
    session.clear()

    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not password:
            flash("Username and password are required.", "danger")
            return render_template("register.html")

        if password != confirm_password:
            flash("The passwords do not match.", "danger")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
            return render_template("register.html")

        database = get_database_session()

        created = database.createUser({"username": username, "password": password})

        if created is False:
            flash("That username is already being used.", "danger")
            return render_template("register.html")

        flash("Account created successfully. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/doctor/<doctor_uuid>/review", methods=["GET", "POST"])
def submit_review(doctor_uuid):
    if "username" not in session:
        flash(
            "You must log in before writing a review.",
            "warning"
        )
        return redirect(url_for("login"))

    database = get_database_session()
    
    current_doctor = database.getLinkedDoctorProfile(session["username"])

    if current_doctor is not None and current_doctor["doctor"]["uuid"] == doctor_uuid:
        flash(
            "Your account is not connected to a doctor profile.",
            "warning"
        )
        return render_template(
            "submit_review.html",
            doctor=doctor
        )
    
    profile = database.getDoctorProfile(doctor_uuid)
    
    if profile is None:
        abort(404)

    doctor = dict(profile["doctor"])

    if request.method == "POST":
        rating_text = request.form.get("rating", "").strip()
        body = request.form.get("body", "").strip()

        if not rating_text or not body:
            flash(
                "A rating and review are required.",
                "danger"
            )
            return render_template(
                "submit_review.html",
                doctor=doctor
            )

        try:
            rating = int(rating_text)

        except ValueError:
            flash(
                "The rating must be a number from 1 to 5.",
                "danger"
            )
            return render_template(
                "submit_review.html",
                doctor=doctor
            )

        if rating < 1 or rating > 5:
            flash(
                "The rating must be between 1 and 5.",
                "danger"
            )
            return render_template(
                "submit_review.html",
                doctor=doctor
            )

        review = {
            "rating": rating,
            "body": body,
            "helpful_votes": 0
        }

        try:
            database.createReview(
                review,
                {"uuid": doctor_uuid}
            )

        except Exception as error:
            print("createReview error:", error)

            flash(
                "The review could not be submitted.",
                "danger"
            )
            return render_template(
                "submit_review.html",
                doctor=doctor
            )

        flash(
            "Your review has been submitted successfully.",
            "success"
        )

        return redirect(
            url_for(
                "doctor_profile",
                doctor_uuid=doctor_uuid
            )
        )

    return render_template(
        "submit_review.html",
        doctor=doctor
    )



@app.get("/profile")
def user_profile():
    if "username" not in session:
        flash("You must log in to view your profile.", "warning")
        return redirect(url_for("login"))
    username = session["username"]

    database = get_database_session()
    reviews = database.getUserReviews(username)

    return render_template("user_profile.html", username = username, reviews = reviews)

@app.post("/review/<review_uuid>/delete")
def delete_review(review_uuid):
    if "username" not in session:
        flash(
            "You must log in to delete a review.",
            "warning"
        )
        return redirect(url_for("login"))

    database = get_database_session()

    try:
        deleted = database.deleteUserReview(
            session["username"],
            review_uuid
        )

    except Exception as error:
        print("deleteUserReview error:", error)

        flash(
            "The review could not be deleted.",
            "danger"
        )
        return redirect(url_for("user_profile"))

    if not deleted:
        flash(
            "The review was not found or does not belong to you.",
            "danger"
        )
        return redirect(url_for("user_profile"))

    flash(
        "Your review was deleted successfully.",
        "success"
    )
    return redirect(url_for("user_profile"))

@app.post(
    "/doctor/<doctor_uuid>/review/<review_uuid>/report"
)
def report_review(doctor_uuid, review_uuid):
    if "username" not in session:
        flash(
            "You must log in before reporting a review.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "patient":
        abort(403)

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash(
            "A reason for the report is required.",
            "danger"
        )
        return redirect(
            url_for(
                "doctor_profile",
                doctor_uuid=doctor_uuid
            )
        )

    database = get_database_session()

    try:
        database.createReport(
            {"uuid": review_uuid},
            reason
        )

    except Exception as error:
        print("createReport error:", error)

        flash(
            "The review could not be reported.",
            "danger"
        )
        return redirect(
            url_for(
                "doctor_profile",
                doctor_uuid=doctor_uuid
            )
        )

    flash(
        "The review was reported to an administrator.",
        "success"
    )

    return redirect(
        url_for(
            "doctor_profile",
            doctor_uuid=doctor_uuid
        )
    )

@app.teardown_appcontext
def close_database_session(error=None):
    database = g.pop("database_session", None)

    if database is not None:
        database.driver.close()

@app.get("/admin")
def admin_dashboard():
    if "username" not in session:
        flash(
            "You must log in to view the admin dashboard.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        abort(403)

    database = get_database_session()

    users = database.getAllUsers()
    verification_requests = (
        database.getVerificationRequests()
    )
    reports = database.getReports()

    return render_template(
        "admin_dashboard.html",
        users=users,
        verification_requests=verification_requests,
        reports=reports
    )

@app.post("/admin/review/<review_uuid>/delete")
def admin_delete_reported_review(review_uuid):
    if "username" not in session:
        flash(
            "You must log in to manage reported reviews.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        abort(403)

    database = get_database_session()

    try:
        deleted = database.deleteReviewByUuid(
            review_uuid
        )

    except Exception as error:
        print("deleteReviewByUuid error:", error)

        flash(
            "The reported review could not be deleted.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    if not deleted:
        flash(
            "The reported review could not be found.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    flash(
        "The reported review was deleted.",
        "success"
    )

    return redirect(url_for("admin_dashboard"))

@app.post(
    "/admin/report/<reporter_username>/<review_uuid>/dismiss"
)
def dismiss_report(reporter_username, review_uuid):
    if "username" not in session:
        flash(
            "You must log in to manage reported reviews.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        abort(403)

    database = get_database_session()

    try:
        database.dismissReport(
            reporter_username,
            review_uuid
        )

    except Exception as error:
        print("dismissReport error:", error)

        flash(
            "The report could not be dismissed.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    flash(
        "The report was dismissed.",
        "success"
    )

    return redirect(url_for("admin_dashboard"))


@app.post("/admin/users/<username>/role")
def update_user_role(username):
    if "username" not in session:
        flash(
            "You must log in to manage users.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        abort(403)

    new_role = request.form.get("role", "").strip()

    if new_role == "doctor":
        flash(
            "Doctor accounts must be approved through the verification process.",
            "warning"
        )
        return redirect(url_for("admin_dashboard"))

    valid_roles = {
        "patient",
        "admin"
    }

    if new_role not in valid_roles:
        flash(
            "The selected role is invalid.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    # Prevent the current admin from accidentally
    # removing their own admin access.
    if username == session["username"]:
        flash(
            "You cannot change your own role.",
            "warning"
        )
        return redirect(url_for("admin_dashboard"))

    database = get_database_session()

    try:
        updated = database.updateUserRole(
            username,
            new_role
        )

    except Exception as error:
        print("updateUserRole error:", error)

        flash(
            "The user's role could not be updated.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    if not updated:
        flash(
            "The user could not be found.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    flash(
        f"{username} is now a {new_role}.",
        "success"
    )

    return redirect(url_for("admin_dashboard"))

@app.post(
    "/admin/verification/<username>/<doctor_uuid>/approve"
)
def approve_verification(username, doctor_uuid):
    if "username" not in session:
        flash(
            "You must log in to manage verification requests.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        abort(403)

    database = get_database_session()

    try:
        approved = database.approveVerification(
            {"username": username},
            {"uuid": doctor_uuid}
        )

    except Exception as error:
        print("approveVerification error:", error)

        flash(
            "The verification request could not be approved.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    if not approved:
        flash(
            "The verification request could not be approved.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    flash(
        f"{username} was verified as a doctor.",
        "success"
    )

    return redirect(url_for("admin_dashboard"))


@app.post(
    "/admin/verification/<username>/<doctor_uuid>/deny"
)
def deny_verification(username, doctor_uuid):
    if "username" not in session:
        flash(
            "You must log in to manage verification requests.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "admin":
        abort(403)

    database = get_database_session()

    try:
        database.denyVerification(
            {"username": username},
            {"uuid": doctor_uuid}
        )

    except Exception as error:
        print("denyVerification error:", error)

        flash(
            "The verification request could not be denied.",
            "danger"
        )
        return redirect(url_for("admin_dashboard"))

    flash(
        f"The verification request from {username} was denied.",
        "success"
    )

    return redirect(url_for("admin_dashboard"))

@app.post("/doctor/<doctor_uuid>/claim")
def claim_doctor_profile(doctor_uuid):
    if "username" not in session:
        flash(
            "You must log in before claiming a doctor profile.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "patient":
        flash(
            "Only patient accounts can submit verification requests.",
            "warning"
        )
        return redirect(
            url_for(
                "doctor_profile",
                doctor_uuid=doctor_uuid
            )
        )

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash(
            "Please provide verification information.",
            "danger"
        )
        return redirect(
            url_for(
                "doctor_profile",
                doctor_uuid=doctor_uuid
            )
        )

    database = get_database_session()
    profile = database.getDoctorProfile(doctor_uuid)

    if profile is None:
        abort(404)

    try:
        database.requestVerification(
            {"uuid": doctor_uuid},
            reason
        )

    except Exception as error:
        print("requestVerification error:", error)

        flash(
            "The verification request could not be submitted.",
            "danger"
        )
        return redirect(
            url_for(
                "doctor_profile",
                doctor_uuid=doctor_uuid
            )
        )

    flash(
        "Your verification request was submitted.",
        "success"
    )

    return redirect(
        url_for(
            "doctor_profile",
            doctor_uuid=doctor_uuid
        )
    )

@app.get("/doctor-dashboard")
def doctor_dashboard():
    if "username" not in session:
        flash(
            "You must log in to view the doctor dashboard.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "doctor":
        abort(403)

    database = get_database_session()

    profile = database.getLinkedDoctorProfile(
        session["username"]
    )

    if profile is None:
        flash(
            "Your account is not connected to a doctor profile.",
            "warning"
        )
        return redirect(url_for("index"))

    doctor = dict(profile["doctor"])
    reviews = profile.get("reviews", [])

    reviews.sort(
        key=lambda review: review.get("date", ""),
        reverse=True
    )

    for review in reviews:
        review["comments"] = database.getComments(
            review["uuid"]
        )

    doctor["average_rating"] = (
        profile.get("average_rating") or 0
    )

    doctor["review_count"] = len(reviews)

    return render_template(
        "doctor_dashboard.html",
        doctor=doctor,
        hospital=profile.get("hospital"),
        reviews=reviews
    )

@app.post("/doctor/review/<review_uuid>/respond")
def respond_to_review(review_uuid):
    if "username" not in session:
        flash(
            "You must log in before responding to a review.",
            "warning"
        )
        return redirect(url_for("login"))

    if session.get("role") != "doctor":
        abort(403)

    response_body = request.form.get(
        "response_body",
        ""
    ).strip()

    if not response_body:
        flash(
            "A response is required.",
            "danger"
        )
        return redirect(url_for("doctor_dashboard"))

    database = get_database_session()

    allowed = database.canDoctorRespondToReview(
        session["username"],
        review_uuid
    )

    if not allowed:
        abort(403)

    try:
        database.createComment(
            response_body,
            review_uuid
        )

    except Exception as error:
        print("createComment error:", error)

        flash(
            "The response could not be submitted.",
            "danger"
        )
        return redirect(url_for("doctor_dashboard"))

    flash(
        "Your response was submitted successfully.",
        "success"
    )

    return redirect(url_for("doctor_dashboard"))

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5001,
        debug=False
    )

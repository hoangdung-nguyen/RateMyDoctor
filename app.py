from flask import Flask, render_template, request, abort
from database import AUTH, Session

app = Flask(__name__)

database_session = Session(AUTH)

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/search")
def search_results():
    search_term = request.args.get("q", "").strip()
    doctors = []

    if search_term:
        raw_results = database_session.search(search_term)

        for row in raw_results:
            doctor = row[0]

            # search() can return both doctors and hospitals.
            # Doctors have a specialty property.
            if "specialty" not in doctor:
                continue

            doctor_identifier = {
                "uuid": doctor["uuid"]
            }

            rating = database_session.getDoctorRating(
                doctor_identifier
            )

            reviews = database_session.getDoctorReviews(
                doctor_identifier
            )

            doctor["average_rating"] = rating or 0
            doctor["review_count"] = len(reviews)

            doctors.append(doctor)

    return render_template(
        "search_results.html",
        search_term=search_term,
        doctors=doctors
    )


@app.get("/doctor/<doctor_uuid>")
def doctor_profile(doctor_uuid):
    profile = get_doctor_profile(doctor_uuid)

    if profile is None:
        abort(404)

    return render_template(
        "doctor_profile.html",
        doctor=profile["doctor"],
        hospital=profile["hospital"],
        reviews=profile["reviews"]
    )


if __name__ == "__main__":
    app.run(debug=True)
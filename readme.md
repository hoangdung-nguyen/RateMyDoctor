# Instructions
>[!warning]
> Running db/setup.py will delete all nodes and users on an existing database.
> I could not specify a sub-database to run commands on since we used the free version of neo4j.
 - export environment variables:
    - NEO4J_URI
    - NEO4J_USERNAME
    - NEO4J_PASSWORD
 - run db/setup.py
    - import data
 - run app.py
    - admin  = {user:'admin_test', pass:'password'}
    - doctor = {user:'doctor_test', pass:'password'}
        - The doctor will not be a doctor by default, must be promoted by an admin after requesting verification

---

# RateMyDoctor
- Proposed features:
	- Rate Hospitals
	- Subcategory scores
	- Comment based feedback
	- Doctors can respond to user comments
	- Group Doctors by hospital
	- Group by procedure (Might be out of scope)
	- Search for doctor/hosptial
	- Distance based filtering
- User-Access-Roles:
	- User
		- View & Leave Reviews
		- Access non-user location data
	- Doctor/Hospital
		- Request audit of review
		- Respond to reviews
	- Admin
		- Verify status of a doctor
		- Moderate reviews
- Project Roles
	- All members will work on the backend where relavant
	- @adrianaprz13
		- UI-UX
	- @hoangdung-nguyen 
		- Data Collections
	- @AbyssalNewt
		- Database Managent
- Note:
	- App may change to "Rate my Hospital" depending on the difficulty of data management with different API's

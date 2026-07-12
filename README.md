# Trekking Management App - Project

## Description

Trekking Management App is a multi-user Flask web application designed to manage trekking routes, staff assignments, trek bookings, and user trekking history. It supports three types of users: **Admins**, **Staff**, and **Trekkers**. Admins manage the complete system, Staff members manage only assigned treks, and Trekkers can browse, book, and track trekking activities.

## Key Features

- User authentication and role-based access
- Trek creation, editing, assignment, and deletion
- Staff registration, approval, blacklist, and restore workflow
- Trekker registration and booking management
- Trek availability and slot tracking
- Booking history and participant tracking
- Admin search across treks, users, and staff
- JSON API-based interaction for treks, bookings, and users

## Frameworks and Libraries Used

### Backend

- **Flask** - Web application and API management
- **Flask-Login** - User authentication and session management
- **Flask-SQLAlchemy** - ORM for database management
- **SQLite** - Lightweight database storage
- **Werkzeug** - Secure password hashing

### Frontend

- **HTML, CSS, Bootstrap** - Responsive UI design
- **Jinja2** - Template rendering
- **Custom CSS** - Application-specific styling

## Database Schema

### User Table

- id (Primary Key)
- name
- email
- phone
- password_hash
- role
- status
- is_approved
- created_at

### Trek Table

- id (Primary Key)
- trek_name
- location
- difficulty
- duration_days
- total_slots
- available_slots
- description
- start_date
- end_date
- status
- assigned_staff_id (Foreign Key)
- created_at

### Booking Table

- id (Primary Key)
- user_id (Foreign Key)
- trek_id (Foreign Key)
- booking_date
- status
- payment_status
- updated_at

### StaffProfile Table

- id (Primary Key)
- user_id (Foreign Key)
- experience_years
- specialization
- emergency_contact
- bio
- created_at
- updated_at

## Approach Used

### Role-Based Access Control (RBAC)

- **Admins**: Create, edit, delete, and assign treks; approve or blacklist staff; manage users and bookings.
- **Staff**: View and manage only assigned treks, update trek status and available slots, and view participants.
- **Trekkers**: Browse open treks, book available slots, cancel bookings, update profile, and view history.

### Authentication

Secure login and registration are implemented using **Flask-Login**. Passwords are hashed with **Werkzeug** before being stored in the database. Admin access is seeded through the application setup.

### Data Management

**SQLite** stores users, staff profiles, treks, and bookings. SQLAlchemy relationships connect users with bookings, staff with assigned treks, and treks with their participants.

## Features and Functionalities

### User Authentication

- Login and logout for all roles
- Trekker registration
- Staff registration with admin approval
- Profile update support

### Admin Management

- Dashboard with trek, user, staff, and booking counts
- Create, edit, assign, and delete treks
- Approve, blacklist, or restore staff accounts
- Review and manage trekker accounts
- View all bookings
- Search treks, users, and staff

### Staff Management

- Staff dashboard for assigned treks
- Update trek status and available slots
- View participants for assigned treks
- Maintain staff profile details such as experience, specialization, and emergency contact

### Trekker Booking

- Browse open treks
- Filter treks by difficulty and location
- View detailed trek information
- Book treks with available slots
- Cancel active bookings
- View complete trekking history

### API Interaction

- `GET /api/treks`
- `GET /api/treks/<id>`
- `PUT /api/treks/<id>`
- `GET, POST /api/bookings`
- `GET, DELETE /api/bookings/<id>`
- `GET /api/users`
- `GET, PATCH /api/users/<id>`

## Application Architecture

- **Backend:** Python Flask application using SQLAlchemy ORM for database operations and route-based API handling.
- **Frontend:** Bootstrap, HTML, CSS, and Jinja2 templates for role-specific dashboards and forms.
- **Database:** SQLite database storing user accounts, staff profiles, trek records, and booking history.
- **Security:** Login sessions through Flask-Login, password hashing through Werkzeug, and route-level role checks.

## Run Locally

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Start the application:

   ```bash
   python app.py
   ```

3. Open the application in your browser and use the login or registration options.

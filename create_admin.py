from app import ADMIN_PASSWORD, app, ensure_schema_updates, seed_admin_user


def main():
    with app.app_context():
        ensure_schema_updates()
        seed_admin_user()
    print("Predefined admin user is ready.")
    print("Login ID: admin")
    print("Email: admin@local")
    print(f"Password: {ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()

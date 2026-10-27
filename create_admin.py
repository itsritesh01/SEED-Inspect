
import getpass
import sys

from app import create_app
from app.setup_admin import create_first_administrator


def main():
    print("Create the first SEED Inspect administrator.")
    print("There is no public registration page.")
    print("The password will not appear as you type.")
    full_name = input("Full name: ")
    email = input("Email: ")
    password = getpass.getpass("Password: ")
    repeat = getpass.getpass("Repeat password: ")

    app = create_app()
    with app.app_context():
        user, error = create_first_administrator(full_name, email, password, repeat)
        created_email = user.email if user else None

    if error:
        print(error)
        print("No account was created.")
        return 1

    print("Administrator created.")
    print("Email:", created_email)
    print("The password was stored only in scrambled form.")
    print("Next, run python run.py and open http://127.0.0.1:5000/login")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print("Stopped. If you did not see Administrator created, no account was saved.")
        sys.exit(1)

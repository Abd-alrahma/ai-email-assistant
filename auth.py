import pandas as pd


USERS_FILE = "data/users.csv"


def authenticate_user(user_id: str):
    """
    Authenticate a user using their User ID
    and return their permissions.
    """

    users = pd.read_csv(USERS_FILE)

    # Remove accidental spaces from User IDs
    users["user_id"] = users["user_id"].astype(str).str.strip()
    user_id = user_id.strip()

    # Find the user
    user = users[users["user_id"] == user_id]

    # User not found
    if user.empty:
        return None

    # Convert the row to a dictionary
    user = user.iloc[0]

    return {
        "user_id": user["user_id"],
        "name": user["name"],
        "email": user["email"],
        "can_read_email": bool(user["can_read_email"]),
        "can_send_email": bool(user["can_send_email"]),
        "can_reply_email": bool(user["can_reply_email"]),
    }


if __name__ == "__main__":

    user_id = input("Enter your User ID: ")

    user = authenticate_user(user_id)

    if user is None:
        print("\nAuthentication failed.")
        print("User ID not found.")

    else:
        print("\nAuthentication successful!")
        print(f"User: {user['name']}")
        print(f"Email: {user['email']}")

        print("\nPermissions:")
        print(f"Read Email:  {user['can_read_email']}")
        print(f"Send Email:  {user['can_send_email']}")
        print(f"Reply Email: {user['can_reply_email']}")
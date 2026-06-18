import streamlit as st

# --- LOGIN SECTION ---
st.title("Welcome to My App")

# Static credentials
USERNAME = "admin"
PASSWORD = "12345"

# Session state to keep user logged in
if "login_success" not in st.session_state:
    st.session_state.login_success = False

# Show login form only if not logged in
if not st.session_state.login_success:
    st.subheader("Please log in to access the app")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    login_button = st.button("Login")

    if login_button:
        if username == USERNAME and password == PASSWORD:
            st.success("Login successful!")
            st.session_state.login_success = True
            st.experimental_rerun()  # Refresh to show the main app
        else:
            st.error("Invalid username or password")
else:
    # --- MAIN APP FUNCTIONALITY ---
    st.subheader("Main App Content")
    st.write("Here is the main functionality of your app.")
    # Your existing app code can continue here...

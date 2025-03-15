# Session and Token Constants
SESSION_EXPIRY_SECONDS = 3600  # 1 hour
TOKEN_EXPIRY_HOURS = 1

# Database Constants
COCKROACHDB_USERS_TABLE = "users"
MONGODB_LICENSES_COLLECTION = "user_licenses"

# Error Messages
ERROR_MISSING_FIELDS = "All fields are required"
ERROR_USER_EXISTS = "Username already exists"
ERROR_USER_NOT_FOUND = "User not found"
ERROR_INVALID_CREDENTIALS = "Invalid username or password"
ERROR_UNAUTHORIZED_ACCESS = "Unauthorized access"
ERROR_SESSION_EXPIRED = "Session expired. Log in again"
ERROR_DATABASE = "Database error"
ERROR_UNEXPECTED = "An unexpected error occurred"

# Success Messages
SUCCESS_REGISTRATION = "Registration successful"
SUCCESS_LOGIN = "Login successful"
SUCCESS_LOGOUT = "Logout successful"
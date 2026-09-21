EVENT_TYPE_LOGIN = "login"
EVENT_TYPE_LOGOUT = "logout"
EVENT_TYPE_LOGIN_FAILED = "login_failed"
EVENT_TYPE_SESSION_EXPIRED = "session_expired"
EVENT_TYPE_PID_VIEW = "pid_view"

EVENT_TYPE_CHOICES = [
    (EVENT_TYPE_LOGIN, "Login"),
    (EVENT_TYPE_LOGOUT, "Logout"),
    (EVENT_TYPE_LOGIN_FAILED, "Login failed"),
    (EVENT_TYPE_SESSION_EXPIRED, "Session expired"),
    (EVENT_TYPE_PID_VIEW, "Participant identifiers viewed"),
]

AUTH_METHOD_LOCAL = "local"
AUTH_METHOD_OIDC = "oidc"
AUTH_METHOD_MFA = "mfa"

AUTH_METHOD_CHOICES = [
    (AUTH_METHOD_LOCAL, "Local"),
    (AUTH_METHOD_OIDC, "OIDC"),
    (AUTH_METHOD_MFA, "MFA"),
]

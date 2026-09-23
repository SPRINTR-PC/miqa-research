EVENT_TYPE_LOGIN = "login"
EVENT_TYPE_LOGOUT = "logout"
EVENT_TYPE_LOGIN_FAILED = "login_failed"
EVENT_TYPE_SESSION_EXPIRED = "session_expired"
EVENT_TYPE_PID_VIEW = "pid_view"
EVENT_TYPE_ETL_SCRIPT_CREATED = "etl_script_created"
EVENT_TYPE_ETL_SCRIPT_UPDATED = "etl_script_updated"
EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED = "etl_script_version_created"
EVENT_TYPE_ETL_SCRIPT_ARCHIVED = "etl_script_archived"
EVENT_TYPE_ETL_BINDING_CREATED = "etl_binding_created"
EVENT_TYPE_ETL_SETTINGS_UPDATED = "etl_settings_updated"

EVENT_TYPE_CHOICES = [
    (EVENT_TYPE_LOGIN, "Login"),
    (EVENT_TYPE_LOGOUT, "Logout"),
    (EVENT_TYPE_LOGIN_FAILED, "Login failed"),
    (EVENT_TYPE_SESSION_EXPIRED, "Session expired"),
    (EVENT_TYPE_PID_VIEW, "Participant identifiers viewed"),
    (EVENT_TYPE_ETL_SCRIPT_CREATED, "ETL script created"),
    (EVENT_TYPE_ETL_SCRIPT_UPDATED, "ETL script updated"),
    (EVENT_TYPE_ETL_SCRIPT_VERSION_CREATED, "ETL script version created"),
    (EVENT_TYPE_ETL_SCRIPT_ARCHIVED, "ETL script archived"),
    (EVENT_TYPE_ETL_BINDING_CREATED, "ETL pipeline binding created"),
    (EVENT_TYPE_ETL_SETTINGS_UPDATED, "ETL project settings updated"),
]

AUTH_METHOD_LOCAL = "local"
AUTH_METHOD_OIDC = "oidc"
AUTH_METHOD_MFA = "mfa"

AUTH_METHOD_CHOICES = [
    (AUTH_METHOD_LOCAL, "Local"),
    (AUTH_METHOD_OIDC, "OIDC"),
    (AUTH_METHOD_MFA, "MFA"),
]

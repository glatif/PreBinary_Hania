# =============================================================================
# db.py — Prebinary
# =============================================================================
# Database connection module.
#
# Two connection strategies are provided:
#   - get_connection(): returns a raw mysql.connector connection, used in
#     auth.py for all transactional writes (inserts, updates, deletes).
#   - get_engine(): returns an SQLAlchemy Engine, required by Pandas
#     (pd.read_sql) and Streamlit's st.data_editor to avoid deprecation
#     warnings with raw DBAPI connections.
#
# Both use the same credentials from DB_CONFIG. The engine is constructed
# on every call rather than cached at module level to avoid stale connection
# state across Streamlit reruns.
# =============================================================================

import mysql.connector
from sqlalchemy import create_engine


# =============================================================================
# CONNECTION CONFIGURATION
# =============================================================================

DB_CONFIG = {
    "host":     "localhost",
    "user":     "streamlit_user",
    "password": "streamlit_pass",
    "database": "streamlit_database",
}


# =============================================================================
# CONNECTION FACTORIES
# =============================================================================

def get_connection():
    """
    Return a raw mysql.connector connection using DB_CONFIG.

    Used in auth.py for all write operations (inserts, updates, deletes).
    Callers are responsible for calling cursor.close() and conn.close() after
    use, typically via a try/finally block to guarantee cleanup even on error.
    """
    return mysql.connector.connect(**DB_CONFIG)


def get_engine():
    """
    Return an SQLAlchemy Engine using DB_CONFIG.

    Required by pd.read_sql() in app.py, which does not accept raw DBAPI
    connections in recent versions of pandas. Also used as the connection
    argument for Streamlit's st.data_editor bulk tables.

    The connection URL is assembled from DB_CONFIG at call time so that any
    credential changes take effect without restarting the application.
    """
    url = (
        f"mysql+mysqlconnector://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    )
    return create_engine(url)
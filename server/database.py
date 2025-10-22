"""
Module with PostgreSQL helpers
"""

import os
import psycopg2
import threading
from psycopg2.extras import RealDictCursor

from flask import g

from __init__ import app


schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')

# Database configuration
db_host = os.getenv('DB_HOST', 'postgres')
db_port = os.getenv('DB_PORT', '5432')
db_name = os.getenv('DB_NAME', 'farmdb')
db_user = os.getenv('DB_USER', 'farm')
db_password = os.getenv('DB_PASSWORD', 'asdasdasd')

_init_started = False
_init_lock = threading.RLock()


def dict_factory(cursor, row):
    """
    Convert database row to dictionary similar to sqlite3.Row
    """
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def get(context_bound=True):
    """
    If there is no opened connection to the PostgreSQL database in the context
    of the current request or if context_bound=False, get() opens a new
    connection to the PostgreSQL database. Reopening the connection on each request
    may have some overhead, but allows to avoid implementing a pool of
    thread-local connections.

    If the database schema needs initialization, get() creates and initializes it.
    If get() is called from other threads at this time, they will wait
    for the end of the initialization.

    If context_bound=True, the connection will be closed after
    request handling (when the context will be destroyed).

    :returns: a connection to the initialized PostgreSQL database
    """

    global _init_started

    if context_bound and 'database' in g:
        return g.database

    # Connect to PostgreSQL database
    database = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_password
    )

    # Check if initialization is needed
    need_init = check_if_initialization_needed(database)

    if need_init:
        with _init_lock:
            if not _init_started:
                _init_started = True
                _init(database)

    if context_bound:
        g.database = database
    
    app.logger.info('DB connection established')
    return database


def check_if_initialization_needed(conn):
    """
    Check if database needs initialization by looking for specific tables.
    Modify this based on your application's requirements.
    """
    try:
        cursor = conn.cursor()
        # Check for existence of any table to see if DB is initialized
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public'
                LIMIT 1
            );
        """)
        tables_exist = cursor.fetchone()[0]
        cursor.close()
        return not tables_exist
    except Exception as e:
        app.logger.error(f"Error checking initialization status: {e}")
        return True


def _init(conn):
    """
    Initialize the database schema and any required data.
    """
    try:
        cursor = conn.cursor()
        
        # Read and execute schema.sql if it exists
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            cursor.execute(schema_sql)
            app.logger.info("Executed schema.sql")
        else:
            # Fallback to basic tables if schema.sql doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS flags (
                    id SERIAL PRIMARY KEY,
                    flag TEXT UNIQUE NOT NULL,
                    team INTEGER NOT NULL,
                    tick INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id SERIAL PRIMARY KEY,
                    flag TEXT NOT NULL,
                    team INTEGER NOT NULL,
                    tick INTEGER NOT NULL,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        
        conn.commit()
        cursor.close()
        app.logger.info("Database initialized successfully")
        
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Database initialization failed: {e}")
        raise


def query(sql, args=()):
    """
    Execute a query and return results as dictionaries
    """
    conn = get()
    cursor = conn.cursor()
    cursor.execute(sql, args)
    
    if cursor.description:  # If it's a SELECT query
        results = [dict_factory(cursor, row) for row in cursor.fetchall()]
    else:  # For INSERT, UPDATE, DELETE
        results = None
        conn.commit()
    
    cursor.close()
    return results


def execute(sql, args=()):
    """
    Execute a query that doesn't return results (INSERT, UPDATE, DELETE)
    """
    conn = get()
    cursor = conn.cursor()
    cursor.execute(sql, args)
    conn.commit()
    cursor.close()


def fetch_one(sql, args=()):
    """
    Execute a query and return first result as dictionary
    """
    conn = get()
    cursor = conn.cursor()
    cursor.execute(sql, args)
    
    if cursor.description:  # If it's a SELECT query
        row = cursor.fetchone()
        result = dict_factory(cursor, row) if row else None
    else:
        result = None
        conn.commit()
    
    cursor.close()
    return result


@app.teardown_appcontext
def close(_):
    if 'database' in g:
        g.database.close()

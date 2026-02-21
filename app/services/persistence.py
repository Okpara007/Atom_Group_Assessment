import sqlite3
from app.config import DB_PATH
import uuid

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  
    return conn

def create_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY, 
        owner_username TEXT,
        original_filename TEXT,
        stored_path TEXT,
        content_type TEXT,
        size_bytes INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        current_status TEXT, 
        error_message TEXT
    )
    ''')

    cursor.execute("PRAGMA table_info(documents)")
    columns = {row[1] for row in cursor.fetchall()}
    if "owner_username" not in columns:
        cursor.execute("ALTER TABLE documents ADD COLUMN owner_username TEXT")

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS status_events (
        event_id TEXT PRIMARY KEY,   
        document_id TEXT,            
        status TEXT,                 
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
        metadata TEXT,               
        error_message TEXT,          
        FOREIGN KEY (document_id) REFERENCES documents(document_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS analysis_results (
        document_id TEXT PRIMARY KEY, 
        summary TEXT,                 
        key_topics TEXT,              
        sentiment TEXT,               
        actionable_items TEXT,        
        raw_model_output TEXT,        
        FOREIGN KEY (document_id) REFERENCES documents(document_id)
    )
    ''')

    conn.commit()
    conn.close()

create_tables()

def insert_document_metadata(
    document_id,
    owner_username,
    original_filename,
    stored_path,
    content_type,
    size_bytes,
    status='pending',
    error_message=None,
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO documents (
            document_id,
            owner_username,
            original_filename,
            stored_path,
            content_type,
            size_bytes,
            current_status,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (document_id, owner_username, original_filename, stored_path, content_type, size_bytes, status, error_message))
    conn.commit()
    conn.close()

def insert_status_event(document_id, status, metadata=None, error_message=None):
    event_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO status_events (event_id, document_id, status, metadata, error_message)
        VALUES (?, ?, ?, ?, ?)
    ''', (event_id, document_id, status, metadata, error_message))
    cursor.execute(
        '''
        UPDATE documents
        SET current_status = ?, error_message = ?
        WHERE document_id = ?
        ''',
        (status, error_message, document_id),
    )
    conn.commit()
    conn.close()

def insert_analysis_result(document_id, summary, key_topics, sentiment, actionable_items, raw_model_output=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        '''
        INSERT INTO analysis_results (document_id, summary, key_topics, sentiment, actionable_items, raw_model_output)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
            summary = excluded.summary,
            key_topics = excluded.key_topics,
            sentiment = excluded.sentiment,
            actionable_items = excluded.actionable_items,
            raw_model_output = excluded.raw_model_output
        ''',
        (document_id, summary, key_topics, sentiment, actionable_items, raw_model_output),
    )
    conn.commit()
    conn.close()

def get_document_by_id(document_id, owner_username=None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if owner_username is None:
            cursor.execute('SELECT * FROM documents WHERE document_id = ?', (document_id,))
        else:
            cursor.execute(
                'SELECT * FROM documents WHERE document_id = ? AND owner_username = ?',
                (document_id, owner_username),
            )
        document = cursor.fetchone()
    return document

def get_document_status_history(document_id, owner_username=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if owner_username is None:
        cursor.execute(
            'SELECT * FROM status_events WHERE document_id = ? ORDER BY timestamp ASC',
            (document_id,),
        )
    else:
        cursor.execute(
            '''
            SELECT se.*
            FROM status_events se
            JOIN documents d ON d.document_id = se.document_id
            WHERE se.document_id = ? AND d.owner_username = ?
            ORDER BY se.timestamp ASC
            ''',
            (document_id, owner_username),
        )
    status_history = cursor.fetchall()
    conn.close()
    return status_history

def get_document_analysis_result(document_id, owner_username=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if owner_username is None:
        cursor.execute('SELECT * FROM analysis_results WHERE document_id = ?', (document_id,))
    else:
        cursor.execute(
            '''
            SELECT ar.*
            FROM analysis_results ar
            JOIN documents d ON d.document_id = ar.document_id
            WHERE ar.document_id = ? AND d.owner_username = ?
            ''',
            (document_id, owner_username),
        )
    analysis_result = cursor.fetchone()
    conn.close()
    return analysis_result


def list_documents(owner_username=None, status_filter=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    query = (
        '''
        SELECT document_id, owner_username, original_filename, stored_path, content_type, size_bytes, created_at, current_status, error_message
        FROM documents
        '''
    )
    conditions = []
    params = []

    if owner_username is not None:
        conditions.append("owner_username = ?")
        params.append(owner_username)
    if status_filter is not None:
        conditions.append("current_status = ?")
        params.append(status_filter)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC"

    cursor.execute(query, tuple(params))
    documents = cursor.fetchall()
    conn.close()
    return documents


def delete_document_and_related(document_id, owner_username=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if owner_username is None:
        cursor.execute('SELECT * FROM documents WHERE document_id = ?', (document_id,))
    else:
        cursor.execute(
            'SELECT * FROM documents WHERE document_id = ? AND owner_username = ?',
            (document_id, owner_username),
        )
    document = cursor.fetchone()
    if document is None:
        conn.close()
        return None

    cursor.execute('DELETE FROM status_events WHERE document_id = ?', (document_id,))
    cursor.execute('DELETE FROM analysis_results WHERE document_id = ?', (document_id,))
    cursor.execute('DELETE FROM documents WHERE document_id = ?', (document_id,))
    conn.commit()
    conn.close()
    return document


def get_recent_status_events(limit=50, owner_username=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if owner_username is None:
        cursor.execute(
            '''
            SELECT
                rowid AS row_num,
                event_id,
                document_id,
                status,
                timestamp,
                metadata,
                error_message
            FROM status_events
            ORDER BY rowid DESC
            LIMIT ?
            ''',
            (limit,),
        )
    else:
        cursor.execute(
            '''
            SELECT
                se.rowid AS row_num,
                se.event_id,
                se.document_id,
                se.status,
                se.timestamp,
                se.metadata,
                se.error_message
            FROM status_events se
            JOIN documents d ON d.document_id = se.document_id
            WHERE d.owner_username = ?
            ORDER BY se.rowid DESC
            LIMIT ?
            ''',
            (owner_username, limit),
        )
    rows = cursor.fetchall()
    conn.close()

    return list(reversed(rows))


def get_status_events_after_rowid(last_rowid, limit=200, owner_username=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if owner_username is None:
        cursor.execute(
            '''
            SELECT
                rowid AS row_num,
                event_id,
                document_id,
                status,
                timestamp,
                metadata,
                error_message
            FROM status_events
            WHERE rowid > ?
            ORDER BY rowid ASC
            LIMIT ?
            ''',
            (last_rowid, limit),
        )
    else:
        cursor.execute(
            '''
            SELECT
                se.rowid AS row_num,
                se.event_id,
                se.document_id,
                se.status,
                se.timestamp,
                se.metadata,
                se.error_message
            FROM status_events se
            JOIN documents d ON d.document_id = se.document_id
            WHERE se.rowid > ? AND d.owner_username = ?
            ORDER BY se.rowid ASC
            LIMIT ?
            ''',
            (last_rowid, owner_username, limit),
        )
    rows = cursor.fetchall()
    conn.close()
    return rows

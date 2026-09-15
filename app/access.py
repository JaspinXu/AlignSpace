"""Project-scoped browser sessions and expiring single-use invitations.

Bearer invitations prove possession, not a person's legal identity. Never put
tokens in audit events, request URLs, project state, or exported briefs.
"""
import hashlib
import secrets
import sqlite3
import time

from fastapi import HTTPException


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AccessStore:
    def __init__(self, database_path):
        self.path = database_path
        with sqlite3.connect(self.path) as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS memberships (
                    project_id TEXT, session_hash TEXT, role TEXT,
                    PRIMARY KEY(project_id, role), UNIQUE(project_id, session_hash));
                CREATE TABLE IF NOT EXISTS invitations (
                    token_hash TEXT PRIMARY KEY, project_id TEXT, expires REAL, used INTEGER DEFAULT 0);
                CREATE INDEX IF NOT EXISTS memberships_session ON memberships(session_hash);
                CREATE INDEX IF NOT EXISTS invitations_project ON invitations(project_id);
            ''')

    def register(self, project_id, token):
        with sqlite3.connect(self.path) as db:
            db.execute('INSERT INTO memberships VALUES (?, ?, ?)', (project_id, digest(token), 'homeowner'))

    def role(self, project_id, token):
        with sqlite3.connect(self.path) as db:
            row = db.execute('SELECT role FROM memberships WHERE project_id=? AND session_hash=?',
                             (project_id, digest(token))).fetchone()
        if not row:
            raise HTTPException(403, 'This session does not have access to this project')
        return row[0]

    def projects(self, token):
        with sqlite3.connect(self.path) as db:
            return [r[0] for r in db.execute('SELECT project_id FROM memberships WHERE session_hash=?', (digest(token),))]

    def invite(self, project_id, token):
        if self.role(project_id, token) != 'homeowner':
            raise HTTPException(403, 'Only the homeowner can invite the designer')
        invite = secrets.token_urlsafe(32)
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE invitations SET used=1 WHERE project_id=?', (project_id,))
            db.execute('INSERT INTO invitations VALUES (?, ?, ?, 0)', (digest(invite), project_id, time.time()+86400))
        return invite

    def claim(self, invite, token):
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT project_id FROM invitations WHERE token_hash=? AND used=0 AND expires>?',
                             (digest(invite), time.time())).fetchone()
            if not row:
                raise HTTPException(403, 'Invitation is expired or already used')
            try:
                db.execute('INSERT INTO memberships VALUES (?, ?, ?)', (row[0], digest(token), 'designer'))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Use a separate designer browser session; this project already has this participant or role')
            db.execute('UPDATE invitations SET used=1 WHERE token_hash=?', (digest(invite),))
        return row[0]

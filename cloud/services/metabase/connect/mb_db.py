import os
import psycopg2

mb_db_config = {
    "host": os.getenv("MB_DB_HOST", "localhost"),
    "port": os.getenv("MB_DB_PORT", "5432"),
    "dbname": os.getenv("MB_DB_DBNAME", "metabase"),
    "user": os.getenv("MB_DB_USER", "postgres"),
    "password": os.getenv("MB_DB_PASS", "postgres")
}

class MetabaseDB:
    def __init__(self):
        self.conn = psycopg2.connect(**mb_db_config)
        self.cursor = self.conn.cursor()

    def _mb_get(self, query: str):
        self.cursor.execute(query)
        return self.cursor.fetchone()
    
    def _mb_delete(self, query):
        self.cursor.execute(query)
        self.conn.commit()
    
    def _mb_close(self):
        if 'cursor' in locals():
            self.cursor.close()
        if 'conn' in locals():
            self.conn.close()

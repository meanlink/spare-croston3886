from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models
def migrate():
    Base.metadata.create_all(engine)
    existing={c['name'] for c in inspect(engine).get_columns('datasets')}
    with engine.begin() as conn:
        if 'parent_id' not in existing:
            conn.execute(text('ALTER TABLE datasets ADD COLUMN parent_id INTEGER REFERENCES datasets(id)'))
        if 'provenance' not in existing:
            conn.execute(text('ALTER TABLE datasets ADD COLUMN provenance JSON'))
if __name__=='__main__':migrate()

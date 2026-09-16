from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()


def create_database(url):
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=options)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(engine):
    from fastapi_app.persistence import models_db
    models_db.Base.metadata.create_all(bind=engine)

import databases
import ormar
import sqlalchemy

DATABASE_URL = "mysql://root:mercury@0.0.0.0:3456/mercury"  # TODO: read from .env

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()
engine = sqlalchemy.create_engine(DATABASE_URL)

base_ormar_config = ormar.OrmarConfig(
    database=database,
    metadata=metadata,
    engine=engine,
)

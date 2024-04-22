import databases
import ormar
import sqlalchemy
from infra.config import DATABASE_URL

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()
engine = sqlalchemy.create_engine(DATABASE_URL)

base_ormar_config = ormar.OrmarConfig(
    database=database,
    metadata=metadata,
    engine=engine,
)

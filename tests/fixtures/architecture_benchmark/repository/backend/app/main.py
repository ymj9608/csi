from app.api.routes import Routes
from app.db.session import connect, initialize


def create_application(database=":memory:"):
    connection = connect(database)
    initialize(connection)
    return Routes(connection)

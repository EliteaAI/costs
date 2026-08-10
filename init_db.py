from tools import db


def init_db():
    from .models.model_price import ModelPrice  # noqa: F401
    from .models.costs_setting import CostsSetting  # noqa: F401
    db.get_shared_metadata().create_all(bind=db.engine)

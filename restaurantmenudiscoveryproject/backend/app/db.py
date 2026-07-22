from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Float, ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Embedding size for the local sentence-transformers model (all-MiniLM-L6-v2).
EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


class RestaurantRow(Base):
    __tablename__ = "restaurants"

    place_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    address = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    website = Column(String, nullable=True)
    menu_status = Column(String, nullable=False, default="not_found")

    menu_items = relationship(
        "MenuItemRow", back_populates="restaurant", cascade="all, delete-orphan"
    )


class MenuItemRow(Base):
    __tablename__ = "menu_items"

    id = Column(String, primary_key=True)
    restaurant_id = Column(String, ForeignKey("restaurants.place_id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    currency = Column(String, default="USD")
    category = Column(String, nullable=True)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)

    restaurant = relationship("RestaurantRow", back_populates="menu_items")


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

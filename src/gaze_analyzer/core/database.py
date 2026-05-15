import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()

class Session(Base):
    __tablename__ = 'sessions'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    video_path = Column(String, nullable=False)
    csv_path = Column(String, nullable=False)
    imported_at = Column(DateTime, default=datetime.utcnow)
    rois = relationship("ROI", back_populates="session", cascade="all, delete-orphan")

class ROI(Base):
    __tablename__ = 'rois'
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'))
    name = Column(String, nullable=False)
    dwell_time_ms = Column(Float, default=0.0)
    session = relationship("Session", back_populates="rois")

DB_PATH = 'sqlite:///gaze_analysis.db'
engine = create_engine(DB_PATH)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

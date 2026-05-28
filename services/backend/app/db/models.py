from sqlalchemy import (
    Column, String, Boolean, Text, Integer, BigInteger,
    Numeric, DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.sql import func
from services.backend.app.db.session import Base


class Ticker(Base):
    __tablename__ = "tickers"

    symbol = Column(String(10), primary_key=True)
    name = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    stream_live = Column(Boolean, nullable=False, default=False)
    added_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    notes = Column(Text, nullable=True)


class Bar(Base):
    __tablename__ = "bars"

    # Composite PK matches the unique constraint (symbol, ts, resolution)
    symbol = Column(String(10), ForeignKey("tickers.symbol"), nullable=False, primary_key=True)
    ts = Column(DateTime(timezone=True), nullable=False, primary_key=True)
    resolution = Column(String(5), nullable=False, primary_key=True)
    open = Column(Numeric(12, 4), nullable=False)
    high = Column(Numeric(12, 4), nullable=False)
    low = Column(Numeric(12, 4), nullable=False)
    close = Column(Numeric(12, 4), nullable=False)
    volume = Column(BigInteger, nullable=False)
    flagged = Column(Boolean, nullable=False, default=False)
    source = Column(String(20), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("symbol", "ts", "resolution", name="uq_bars_symbol_ts_resolution"),
        Index("ix_bars_symbol_resolution_ts", "symbol", "resolution", "ts"),
    )


class IngestionLog(Base):
    __tablename__ = "ingestion_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=True)  # null for multi-ticker stream sessions
    mode = Column(String(10), nullable=False)      # stream | fetch
    job_type = Column(String(20), nullable=False)  # eod | intraday_poll | backfill | stream_session
    source = Column(String(20), nullable=True)
    status = Column(String(15), nullable=False)    # ok | partial | failed | reconnecting
    rows_written = Column(Integer, nullable=True, default=0)
    error_msg = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_ingestion_log_symbol_started_at", "symbol", "started_at"),
        Index("ix_ingestion_log_mode", "mode"),
    )

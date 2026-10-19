from __future__ import annotations

import uuid
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import String, Integer, ForeignKey, DateTime, JSON, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def uid(): return str(uuid.uuid4())
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String,primary_key=True,default=uid)
    timezone: Mapped[str] = mapped_column(String,default='Europe/Madrid')
class Player(Base):
    __tablename__ = 'players'
    id: Mapped[str] = mapped_column(String,primary_key=True)
    name: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
class Tournament(Base):
    __tablename__ = 'tournaments'
    id: Mapped[str] = mapped_column(String,primary_key=True)
    name: Mapped[str] = mapped_column(String)
    circuit: Mapped[str] = mapped_column(String,default='premier-padel')
    metadata_: Mapped[dict] = mapped_column('metadata',JSON,default=dict)
class Court(Base):
    __tablename__ = 'courts'
    id: Mapped[str] = mapped_column(String,primary_key=True,default=uid)
    tournament_id: Mapped[str] = mapped_column(ForeignKey('tournaments.id'))
    name: Mapped[str] = mapped_column(String)
class Match(Base):
    __tablename__ = 'matches'
    id: Mapped[str] = mapped_column(String,primary_key=True)
    court_id: Mapped[str] = mapped_column(ForeignKey('courts.id'))
    day: Mapped[str] = mapped_column(String)
    sequence: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    official_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True),nullable=True)
    time_kind: Mapped[str] = mapped_column(String,default='unknown')
    scores: Mapped[list] = mapped_column(JSON,default=list)
class MatchParticipant(Base):
    __tablename__ = 'match_participants'
    match_id: Mapped[str] = mapped_column(ForeignKey('matches.id'),primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey('players.id'),primary_key=True)
    team: Mapped[int] = mapped_column(Integer)
class FavoritePlayer(Base):
    __tablename__ = 'favorite_players'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),primary_key=True)
    player_id: Mapped[str] = mapped_column(ForeignKey('players.id'),primary_key=True)
class NotificationPreference(Base):
    __tablename__ = 'notification_preferences'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'),primary_key=True)
    event_type: Mapped[str] = mapped_column(String,primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean,default=True)
class NotificationEvent(Base):
    __tablename__ = 'notification_events'
    id: Mapped[str] = mapped_column(String,primary_key=True,default=uid)
    audience: Mapped[str] = mapped_column(String,index=True)
    match_id: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    message: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint('audience','match_id','kind','revision'),)
class MatchStatusHistory(Base):
    __tablename__ = 'match_status_history'
    id: Mapped[str] = mapped_column(String,primary_key=True,default=uid)
    match_id: Mapped[str] = mapped_column(String)
    before: Mapped[str] = mapped_column(String)
    after: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

class TrackedMatch(Base):
    __tablename__ = 'tracked_matches'
    id: Mapped[str] = mapped_column(String,primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer,default=1)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class DeviceSubscription(Base):
    __tablename__ = 'device_subscriptions'
    audience: Mapped[str] = mapped_column(String,primary_key=True)
    favorites: Mapped[list] = mapped_column(JSON,default=list)
    enabled: Mapped[bool] = mapped_column(Boolean,default=True)

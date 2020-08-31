#!/usr/bin/env python

from __future__ import unicode_literals
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime
from sqlalchemy import (Column, create_engine, Boolean, Integer, Sequence,
                        String, TIMESTAMP)
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def add_job(jobdir, db):
    s, ins = get_session_instance(db)

    with session_guard(s) as session:
        try:
            job = session.query(Job).filter(Job.jobdir == jobdir).one_or_none()
        except OperationalError:
            ins.create_db()
            job = None

        if job is None:
            job = Job(jobdir=jobdir, active=True)
            session.add(job)
        else:
            job.active = True
            job.started = False

        session.commit()
        return job.id


JobInstance = namedtuple('Job',
                         ['id', 'active', 'started', 'updated_at', 'jobdir'])


def find_jobs(db, active=None, project=None, started=None,
              created_after=None, created_before=None,
              updated_after=None, updated_before=None):
    with session_from_db(db) as session:
        query = session.query(Job)
        if active is not None:
            query = query.filter_by(active=active)
        if project is not None:
            query = query.filter(Job.jobdir.startswith(project))
        if started is not None:
            query = query.filter_by(started=started)
        if created_after is not None:
            query = query.filter(Job.created_at >= created_after)
        if created_before is not None:
            query = query.filter(Job.created_at <= created_before)
        if updated_after is not None:
            query = query.filter(Job.updated_at >= updated_after)
        if updated_before is not None:
            query = query.filter(Job.updated_at <= updated_before)
        res = [JobInstance(job.id, job.active, job.started, job.updated_at,
                           job.jobdir) for job in query.all()]
    return res


def get_jobdir(id, db):
    with session_from_db(db) as session:
        job = session.query(Job).get(id)
        return job.jobdir


def is_started(id, db):
    with session_from_db(db) as session:
        job = session.query(Job).get(id)
        return job.started


SqlBase = declarative_base()


class Job(SqlBase):
    __tablename__ = 'jobs'
    id = Column(Integer, Sequence('user_id_seq'), primary_key=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow,
                        onupdate=datetime.utcnow, nullable=False)
    jobdir = Column(String(512), nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    started = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return "<Job('%s')>" % (self.jobdir)


class JobVault(object):
    def __init__(self, db):
        self.engine = create_engine('sqlite:///'+db)
        self.Session = sessionmaker(bind=self.engine)

    def create_db(self):
        SqlBase.metadata.create_all(self.engine)

    def new_session(self):
        return self.Session()


def get_session_instance(db):
    ins = JobVault(db)
    session = ins.new_session()
    return session, ins


def session_from_db(db):
    session, ins = get_session_instance(db)
    return session_guard(session)


@contextmanager
def session_guard(session):
    try:
        yield session
        session.commit()
    except Exception as ex:
        session.rollback()
        raise ex
    finally:
        session.close()


def set_finished(id, db):
    with session_from_db(db) as session:
        job = session.query(Job).get(id)
        job.started = False
        job.active = False


def set_started(id, db):
    with session_from_db(db) as session:
        job = session.query(Job).get(id)
        job.started = True

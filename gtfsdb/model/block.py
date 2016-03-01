import sys
import time
import logging
log = logging.getLogger(__name__)


from sqlalchemy import Column, Sequence
from sqlalchemy.orm import relationship
from sqlalchemy.types import Integer, String

from gtfsdb import config
from gtfsdb.model.base import Base
from gtfsdb.model.trip import Trip


class Block(Base):
    datasource = config.DATASOURCE_DERIVED

    __tablename__ = 'blocks'

    id = Column(Integer, Sequence(None, optional=True), primary_key=True)
    sequence = Column(Integer)
    block_id = Column(String(255),   index=True, nullable=False)
    service_id = Column(String(255), index=True, nullable=False)
    trip_id = Column(String(255),    index=True, nullable=False)
    prev_trip_id = Column(String(255))
    next_trip_id = Column(String(255))
    start_stop_id = Column(String(255), index=True, nullable=False)
    end_stop_id = Column(String(255), index=True, nullable=False)

    universal_calendar = relationship(
        'UniversalCalendar',
        primaryjoin='Block.service_id==UniversalCalendar.service_id',
        foreign_keys='(Block.service_id)',
        uselist=True, viewonly=True)

    trip = relationship(
        'Trip',
        primaryjoin='Block.trip_id==Trip.trip_id',
        foreign_keys='(Block.trip_id)',
        uselist=False, viewonly=True)

    next_trip = relationship(
        'Trip',
        primaryjoin='Block.next_trip_id==Trip.trip_id',
        foreign_keys='(Block.next_trip_id)',
        uselist=False, viewonly=True)

    prev_trip = relationship(
        'Trip',
        primaryjoin='Block.prev_trip_id==Trip.trip_id',
        foreign_keys='(Block.prev_trip_id)',
        uselist=False, viewonly=True)

    start_stop = relationship(
        'Stop',
        primaryjoin='Stop.stop_id==Block.start_stop_id',
        foreign_keys='(Block.start_stop_id)',
        uselist=False, viewonly=True)

    end_stop = relationship(
        'Stop',
        primaryjoin='Stop.stop_id==Block.end_stop_id',
        foreign_keys='(Block.end_stop_id)',
        uselist=False, viewonly=True)


    def __init__(self, sequence, block_id, service_id, trip_id, prev_trip_id, next_trip_id, start_stop_id, end_stop_id):
        self.sequence = sequence
        self.block_id = block_id
        self.service_id = service_id
        self.trip_id = trip_id
        self.prev_trip_id = prev_trip_id
        self.next_trip_id = next_trip_id
        self.start_stop_id = start_stop_id
        self.end_stop_id = end_stop_id

    @classmethod
    def load(cls, db, **kwargs):
        log.debug('{0}.load (loaded later in post_process)'.format(cls.__name__))
        pass

    @classmethod
    def post_process(cls, db):
        log.debug('{0}.post_process'.format(cls.__name__))
        cls.populate(db)

    @classmethod
    def populate(cls, db):
        ''' loop thru a full trip table and break things into buckets based on service key and block id
        '''
        start_time = time.time()
        batch_size = config.DEFAULT_BATCH_SIZE
        num_recs = 0

        # step 1: loop thru all trips, sorted by block and service key
        #import pdb; pdb.set_trace()
        trips = db.session.query(Trip).order_by(Trip.block_id, Trip.service_id).all()
        i = 0
        while i < len(trips):
            b = trips[i].block_id
            s = trips[i].service_id

            # need block (optional) and service id info ... if we don't have that, continue to next trip
            if b is None or s is None:
                i = i + 1
                continue

            # step 2: grab a batch of trips that have the same block and service id
            t = []
            while i < len(trips):
                if trips[i].block_id != b or \
                   trips[i].service_id != s:
                    break
                t.append(trips[i])
                i = i + 1

            # step 3: sort our bucket
            sorted_blocks = sorted(t, key=lambda t : t.start_time)
            sb_len = len(sorted_blocks) - 1

            # step 4: create block objects
            #import pdb; pdb.set_trace()
            for j, k in enumerate(sorted_blocks):
                prev = None
                next = None
                if j > 0: prev = sorted_blocks[j-1].trip_id
                if j < sb_len: next = sorted_blocks[j+1].trip_id
                block = Block(sequence=j+1, block_id=b, service_id=s,
                              trip_id=k.trip_id, prev_trip_id=prev, next_trip_id=next,
                              start_stop_id=k.start_stop.stop_id, end_stop_id=k.end_stop.stop_id
                        )
                db.session.add(block)

            # step 5: insert in the db
            num_recs = num_recs + sb_len
            if num_recs >= batch_size:
                sys.stdout.write('*')
                db.session.flush()
                db.session.commit()
                num_recs = 0

        # step 5b: (final) insert into the db
        db.session.flush()
        db.session.commit()

        processing_time = time.time() - start_time
        log.debug('{0}.populate ({1:.0f} seconds)'.format(cls.__name__, processing_time))

    @classmethod
    def start_stop_ids(cls, session):
        ''' return an array of distinct starting stop_ids
        '''
        ret_val = []
        blocks = session.query(Block).all()
        for b in blocks:
            if b.start_stop_id not in ret_val:
                ret_val.append(b.start_stop_id)
        return ret_val

    @classmethod
    def end_stop_ids(cls, session):
        ''' return an array of distinct ending stop_ids
        '''
        ret_val = []
        blocks = session.query(Block).all()
        for b in blocks:
            if b.end_stop_id not in ret_val:
                ret_val.append(b.end_stop_id)
        return ret_val

    @classmethod
    def unique_stop_ids(cls, session):
        ''' return an array of unique starting and ending stop_ids
        '''
        ret_val = cls.start_stop_ids(session)
        ends   = cls.end_stop_ids(session)
        for s in ends:
            if s not in ret_val:
                ret_val.append(s)
        return ret_val

# coding: utf-8
from sqlalchemy import Column, ForeignKey, Index, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()
metadata = Base.metadata

class User(Base):
    __tablename__ = 'user'
   
    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False)
    picture = Column(String(250))
    

    @property
    def serialize(self):
       """Return object data in easily serializeable format"""
       return {
           'name'         : self.name,
           'email'        : self.email,
           'picture'      : self.picture,
           'id'           : self.id,
       }

class Category(Base):
    __tablename__ = 'category'

    name = Column(String(250), nullable=False)
    id = Column(Integer, primary_key=True)

    @property
    def serialize(self):
       """Return object data in easily serializeable format"""
       return {
           'name'         : self.name,
           'id'           : self.id
       }

class CatalogItem(Base):
    __tablename__ = 'catalogitem'
    __table_args__ = (
        Index('itemIndex', 'name', 'category_id', unique=True),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    desc = Column(String(250), nullable=False)
    category_id = Column(ForeignKey('category.id'))
    category = relationship(Category, backref='items')

    @property
    def serialize(self):
       """Return object data in easily serializeable format"""
       return {
           'cat-id'       : self.category_id,
           'description'  : self.desc,
           'id'           : self.id,
           'title'        : self.name
       }

engine = create_engine('sqlite:///catalog.db?check_same_thread=False')
 
Base.metadata.create_all(engine)
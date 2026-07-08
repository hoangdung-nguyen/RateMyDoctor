#!/usr/bin/env python3
from neo4j import GraphDatabase
from uuid import uuid4 as uuid
from schema import *

HOST = 'localhost'
PORT = '7687'

AUTH = ('neo4j', 'password') #Needs to only have user creation perms after setup

URI = f'neo4j://{HOST}:{PORT}'

class Session:
    """
    API for interacting with a neo4j database.
    """

    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=AUTH)
        self.auth = None

    def login(self, username, password):
        self.auth = (username, password)
        self.uname = username

    def logout(self):
        self.auth = None
        self.uname = None

    def _query(self, query, **kwargs):
        if self.auth == None:
            return False
        records, summary, keys = self.driver.execute_query(query, auth_=self.auth, **kwargs)
        return records

    @staticmethod
    def _giveUuid(td):
        return (td.update({'uuid':uuid()}))

    def createUser(self, login:UserLogin):
        try:
            #Create user in the DMBS
            self.driver.execute_query("""\
                    CREATE USER $username\
                    SET PASSWORD '$password' CHANGE NOT REQUIRED""",
                **login)

        except: #username taken
            return False 

        #Create user as a database object
        self.driver.execute_query("""\
                CREATE (:User {username: $username})""",
                username=login['username'])

    def _deleteUser(self, username):
        self._query("""DROP USER $user IF EXISTS""", user=username)
        self._query("""MATCH (u:User {username: $user})\
                    DETACH DELETE u""", user=username)

    def createHospital(self, h:Hospital):
        self._query("""CREATE (:Hospital {})""".format(self._giveUuid(h)))

    def createReview(self, score, content, username, uuid):
        r = locals(); r.pop('self')
        h = r.popitem()
        u = r.popitem()
        self._query("""MATCH (h:Hospital|Doctor {}),
                             (u:User {}),
                    CREATE (r:Review {}),
                    (u)-[:Authored]->(r),
                    (r)-[:Targeted]->h"""
                              .format(h,u,r))

if __name__ == '__main__':
    s = Session()
    s.login('neo4j','password')
    s._deleteUser('test')
    rec = s._query("""MATCH (u:User {username: 'test'})\
            RETURN u.username AS name""")
    s.createHospital({'name':'tmh','address':'aaa lane','zip':32304})
    print(rec)

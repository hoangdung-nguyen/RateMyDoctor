#!/usr/bin/env python3
from neo4j import GraphDatabase
from uuid import uuid4 as uuid

HOST = 'localhost'
PORT = '7687'
AUTH = ('neo4j', 'password') # !!!Needs to only have user creation perms after setup!!!
URI = f'neo4j://{HOST}:{PORT}'

A = 'a'
B = 'b'
R = 'r'
MERGE = 'MERGE'

WORKS_AT= 'Works_At'

def _dictQuery(d:dict, name:str="") -> tuple[str,dict]:
    """Formats a dict as a string compatible with neo4j queries.

    Also returns a dict to be passed to kwargs in a _query to maintain
    typing."""

    string = "{" + ''.join([f", {k}: ${name+k}" for k,v in d.items()])
    string = string.replace(", ", "", 1) + '}'   #Gets rid of first comma

    values = {name+k:v for k,v in d.items()}    #replacement dict for _query
    return (string, values)

def _labelQuery(name:str, d:dict, labels:str|list, op='') -> tuple[str,dict]:
    """Formats a dict, label, and neo4j variable into a query line.

    Also returns a dict to be passed to kwargs in a _query to maintain
    typing."""

    if type(labels) is not list:
        labels = [labels]

    string, values = _dictQuery(d, name)
    string = (f'{op} ({name}:{':'.join([l for l in labels])} {string})')
    return (string, values)

def _giveId(name:str) -> str:
    return f"ON CREATE SET {name}.uuid = '{uuid()}'"

class Session:
    """
    API for interacting with a neo4j database.
    """

    def __init__(self, login=None, host=HOST, port=PORT, driverAuth=AUTH):
        self.driver = GraphDatabase.driver(f'neo4j://{host}:{port}', auth=driverAuth)
            #Driver is known to be expensive, use as few as possible
        self.auth = None
        if login is not None:
            self.login(*login)

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
        td.update({'uuid':uuid()})
        return td

    def _abRelMerge(self, alab:str, adic:dict, blab:str, bdic:dict, rlab:str):
        """Creates if not exist nodes a, b, and the relation (a)->[:rlab]->(b)"""

        query, values = "", {}
        a, b = (A,adic,alab),(B,bdic,blab)

        for var in (a,b):
            print(var)
            s,v = _labelQuery(*var, MERGE)
            query = '\n'.join([query, s, _giveId(var[0])])
            values = values | v

        query = '\n'.join([query,
                   f'MERGE ({A})-[{R}:{rlab}]->({B})', f'RETURN {A},{R},{B}'
                   ])
        print('\n', query, '\n\n', values)
        return self._query(query, **values)
    
    def createUser(self, login):
        try:
            #Create user in the DMBS
            self.driver.execute_query("""\
                    CREATE USER $username
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
    def _importDoctor(self, docd, hosd):
        return self._abRelMerge('Doctor', docd, 'Hospital', hosd, WORKS_AT)

if __name__ == '__main__':
    HOS = {'name':'tmh','address':'aaa lane','zip':32304}
    DOC = {'name':'John Smith', 'specialty':'being boring'}
    s = Session(AUTH)

    s.createUser({'username':'unknown','password':'password'})
    for record in s._importDoctor(DOC, HOS):
        print(record.data())

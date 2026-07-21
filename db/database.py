#!/usr/bin/env python3
from datetime import datetime
from neo4j import GraphDatabase
from random import randint
from uuid import uuid4 as uuid

HOST = 'localhost'
PORT = '7687'
AUTH = ('neo4j', 'password') # !!!Needs to only have user creation perms after setup!!!
URI = f'neo4j://{HOST}:{PORT}'

A = 'a'
B = 'b'
R = 'r'

MATCH = 'MATCH'
MERGE = 'MERGE'
WORKS_AT = 'Works_At'
WROTE = 'Wrote'
REVIEWS = 'Reviews'
RESPONDS_TO = 'Responds_To'

USR = 'User'
DOC = 'Doctor'
HOS = 'Hospital'
REV = 'Review'


def _dictQuery(name:str='', d:dict|None=None) -> tuple[str,dict]:
    """Formats a dict as a string compatible with neo4j queries.

    Also returns a dict to be passed to be used for neo4j variable-replacement"""
    
    if d == None or len(d) == 0:
        return ("",{})

    string = "{" + ''.join([f", {k}: ${name+k}" for k in d.keys()])
    string = string.replace(", ", "", 1) + '}'   #Gets rid of first comma

    values = {name+k:v for k,v in d.items()}    #replacement dict for _query
    return (string, values)

def _labelQuery(labels:str|list, name:str = '', d:dict|None = None, op='') -> tuple[str,dict]:
    """Formats a dict, label, and neo4j variable into a query line.

    Also returns a dict to be passed to be used for neo4j variable-replacement"""

    if type(labels) is not list:
        labels = [labels]

    string, values = _dictQuery(name, d)
    string = (f'{op} ({name}:{':'.join([l for l in labels])} {string})')
    return (string, values)

def _giveId(name:str) -> str:
    return f"ON CREATE SET {name}.uuid = '{uuid()}'"

class Session:
    """An API for interacting with a neo4j database."""

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

    def _executeQuery(self, query, **kwargs):
        records, summary, keys = self.driver.execute_query(query, auth_=self.auth, **kwargs)
        return records

    def _abRelMerge(self, alab:str, adic:dict,
                          blab:str, bdic:dict,
                          rlab:str, rdic=None,
                          createA=True, createB=True):
        """Creates if not exist nodes a, b, and the relation (a)->[:rlab]->(b)

        [a/b][lab/dic] = [label/dictionary] of [first/second] object
        r[lab/dic] = [label/dictionary] of relation"""

        query, values = "", {}
        a = ({'name':A,'labels':alab,'d':adic},createA)
        b = ({'name':B,'labels':blab,'d':bdic},createB)

        for var in (a,b):
            s,v = _labelQuery(**var[0], op=(MERGE if var[1] else MATCH))
            query = '\n'.join([query, s, _giveId(var[0]['name']) if var[1] else ''])
            values = values | v

        if rdic != None:
            values['rdic'] = rdic
        query = '\n'.join([query,
                   f'MERGE ({A})-[{R}:{rlab}]->({B})\nRETURN {A},{R},{B}'
                           if rdic == None else
                           f'MERGE ({A})-[{R}:{rlab} {{$rdic}}]->({B})\nRETURN {A},{R},{B}'
                   ])
        return self._executeQuery(query, **values)
    
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

    def deleteUser(self, username):
        self._executeQuery("""DROP USER $user IF EXISTS""", user=username)
        self._executeQuery("""MATCH (u:User {username: $user})\
                    DETACH DELETE u""", user=username)

    def _importDoctor(self, doc, hos):
        reviews = doc.pop(REV)
        r = self._abRelMerge(DOC, doc, HOS, hos, WORKS_AT)
        for rev in reviews:
            rev['date'] = datetime.now()
            r += self._abRelMerge(USR,
                                  {'username': ''.join([chr(randint(65,90)) for _ in range(32)])},
                                  REV, rev, WROTE)
            r += self._abRelMerge(REV, rev, DOC, doc, REVIEWS)
        return r

if __name__ == '__main__':
    s = Session(AUTH)

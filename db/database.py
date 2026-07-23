#!/usr/bin/env python3
from datetime import datetime
from haversine import haversine, Unit
from neo4j import GraphDatabase
from random import randint
from uuid import uuid4 as uuid
from zipcodes import zipcodes

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
REPORTED = 'Reported'
REVIEWS = 'Reviews'
RESPONDS_TO = 'Responds_To'
MIGHT_BE = 'Might_Be'
IS = 'Is'

USR = 'User'
DOC = 'Doctor'
HOS = 'Hospital'
REV = 'Review'

NAME = 'name'
BODY = 'body'
DATE = 'date'
UUID = 'uuid'



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

def giveDate(d:dict)->dict:
    d['date'] = str(datetime.now())
    return d

def _giveId(name:str) -> str:
    return f"ON CREATE SET {name}.uuid = '{uuid()}'"

class Session:
    """An API for interacting with a neo4j database."""

    def __init__(self, login:tuple[str,str]|None=None, host=HOST, port=PORT, driverAuth=AUTH):
        self.driver = GraphDatabase.driver(f'neo4j://{host}:{port}', auth=driverAuth)
        self.auth = login
        if login is not None:
            self.login(*login)

    #=================#
    # Private Methods #
    #=================#

    def _executeQuery(self, query, **kwargs):
        records, summary, keys = self.driver.execute_query(query, auth_=self.auth, **kwargs)
        return [list(r.data().values()) for r in records]

    def _abRel(self, alab:str, adic:dict,
                          blab:str, bdic:dict,
                          rlab:str, rdic=None,
                          createA=True, createB=True,
                          final='RETURN a,r,b'):
        """Creates if not exist nodes a, b, and the relation (a)->[:rlab]->(b)

        [a/b][lab/dic] = [label/dictionary] of [first/second] object
        r[lab/dic] = [label/dictionary] of relation
        final = the last operation"""

        query, values = "", {}
        a = ({'name':A,'labels':alab,'d':adic},createA)
        b = ({'name':B,'labels':blab,'d':bdic},createB)

        for var in (a,b):
            s,v = _labelQuery(**var[0], op=(MERGE if var[1] else MATCH))
            query = '\n'.join([query, s, (_giveId(var[0]['name']) if var[1] else '')])
            values = values | v

        if rdic != None:
            rdic, v = _dictQuery(name=R, d=rdic)
            values = values | v
        query = '\n'.join([query,
                   f'MATCH ({A})-[{R}:{rlab}]->({B})\n{final}'
                           if rdic == None else
                           f'MERGE ({A})-[{R}:{rlab} {rdic}]->({B})\n{final}'
                   ])
        return self._executeQuery(query, **values)

    def _importDoctor(self, doc, hos):
        reviews = doc.pop(REV)
        r = self._abRel(DOC, doc, HOS, hos, WORKS_AT)
        for rev in reviews:
            rev['date'] = str(datetime.now())
            r += self._abRel(USR,
                                  {'username': ''.join([chr(randint(65,90)) for _ in range(32)])},
                                  REV, rev, WROTE)
            r += self._abRel(REV, rev, DOC, doc, REVIEWS)
        return r

    #==================#
    # Public Interface #
    #==================#

    def login(self, username:str, password:str):
        self.auth = (username, password)
        self.uname = {'username':username}

    def logout(self):
        self.auth = None
        self.uname = None
    
    def createUser(self, login:dict):
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

    def createDoctor(self, doctor:dict, hospital:dict):
        self._abRel(DOC, doctor, HOS, hospital, WORKS_AT)

    def createReview(self, review:dict, doctor:dict):
        """Only allows one review per doctor"""
        r = self._abRel(USR, self.uname, REV, {}, WROTE,
                       createA=False, createB=False, final='RETURN b')
        if len(r) > 0:
            s.deleteReview(r[0])

        self._abRel(USR, self.uname, REV, giveDate(review), WROTE)
        self._abRel(REV, review, DOC, doctor, REVIEWS)

    def deleteReview(self, review, user:dict|None=None):
        """Do not specify user if used to delete own review"""
        if user == None:
            user = self.uname
        self._abRel(USR, user, REV, review, WROTE, rdic={},
                    createA=False, createB=False, final='DETACH DELETE b')

    def createComment(self, comment, target):
        target = {'uuid':target['uuid']}

    def createReport(self, review:dict, reason:str):
        self._abRel(USR, self.uname, REV, {'uuid':review['uuid']}, REPORTED, rdic={},
                    createA=False, createB=False, final='DETACH DELETE r')
        report = {BODY:reason, DATE:str(datetime.now())}
        self._abRel(USR, self.uname, REV, review, REPORTED, rdic=report, createB=False, createA=False)

    def getReports(self):
        result = self._executeQuery(f"""MATCH (u:{USR})-[r:{REPORTED}]->(c)
                                    RETURN u,r,r.body,c """)
        return [{'reporter':r[0],'reason':r[2],'reportedContent':r[3]} for r in result]

    def requestVerification(self, doctor, reason):
        self._abRel(USR, self.uname, DOC, doctor, MIGHT_BE, {BODY:reason}, createA=False, createB=False)

    def getVerificationRequests(self):
        res = self._abRel(USR,{},DOC,{},MIGHT_BE, createA=False, createB=False,
                          final=f'RETURN a,r,r.{BODY},b')
        return [{'user':r[0],'reason':r[2],'doctor':r[3]} for r in res]

    def approveVerification(self, user, doctor):
        self._abRel(USR,user,DOC,doctor,MIGHT_BE, rdic={}, createA=False, createB=False,
                    final=f'DELETE r')
        self._abRel(USR,user,DOC,doctor,IS, rdic={}, createA=False, createB=False)
        pass
    
    def denyVerification(self, user, doctor):
        self._abRel(USR,user,DOC,doctor,MIGHT_BE, rdic={}, createA=False, createB=False,
                    final=f'DELETE r')
        pass

    def getDoctorRating(self, doctor:dict)->float:
        doc, values = _dictQuery(d=doctor)
        return self._executeQuery(f"""MATCH (:{DOC} {doc})<-[]-(r:{REV})
                                  RETURN avg(toInteger(r.rating))"""
                           , **values)[0][0]

    def getHospitalRating(self, hospital:dict)->float:
        hos, values = _dictQuery(d=hospital)
        return self._executeQuery(f"""MATCH (:{HOS} {hos})<-[]-(d:{DOC})
                                  MATCH (d)<-[]-(r:{REV})
                                  RETURN avg(toInteger(r.rating))"""
                           , **values)[0][0]

    def getDoctorReviews(self, doctor:dict)->list[dict]:
        doc, values = _dictQuery(d=doctor)
        return [i[0] for i in 
                self._executeQuery(f"""MATCH (:{DOC} {doc})<-[]-(r:{REV})
                                  RETURN r """,**values)]

    def getHospitalReviews(self, hospital:dict)->list[dict]:
        hos, values = _dictQuery(d=hospital)
        return [i[0] for i in 
                self._executeQuery(f"""MATCH (:{HOS} {hos})<-[]-(d:{DOC})
                                  MATCH (d)<-[]-(r:{REV})
                                  RETURN r """,**values)]

    def search(self, search:str):
        """Fuzzyfind, most relevant node at index 0"""
        return self._executeQuery(f"""CALL db.index.fulltext.queryNodes('names','{search}')
                                  Yield node return node """)

    def findNear(self, zip:str, range:int)->list:
        """Returns a list of hospitals within range of a zip code"""
        validZips = [z for z, coords, in zipcodes.items()
                 if (haversine(zipcodes[zip], coords, unit=Unit.MILES) <= range)]
        return self._executeQuery(f"MATCH (h:Hospital) WHERE h.zip IN {validZips} RETURN h")

    def _tests(self):
        testdoc = {NAME:'Dr. Kimberly Ireland'}
        print('doc rating', s.getDoctorRating(testdoc) == 4.905000000000001)
        print('doc reviews', len(s.getDoctorReviews(testdoc))==200)
        print('findNear',len(s.findNear('32162',500))==17)
        s.requestVerification(testdoc, 'im witawawy hiwm')
        print('verification', s.getVerificationRequests()[0]['reason'] == 'im witawawy hiwm')
        s.approveVerification(self.uname, testdoc)
        #[print(i) for i in s.getDoctorReviews(s.search('kim ireland')[0][0])]

if __name__ == '__main__':
    s = Session(AUTH)
    s._tests()

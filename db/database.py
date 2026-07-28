#!/usr/bin/env python3
import os
from datetime import datetime
from haversine import haversine, Unit
from neo4j import GraphDatabase
from random import randint
from uuid import uuid4 as uuid
from db.zipcodes import zipcodes    #throws error on Linux from app.py when not prepended with db

HOST = os.environ.get("NEO4J_HOST","localhost")

PORT = os.environ.get("NEO4J_PORT","7687")

URI = os.environ.get("NEO4J_URI",f"neo4j://{HOST}:{PORT}")

AUTH = (
    os.environ.get("NEO4J_USERNAME","neo4j"),
    os.environ.get("NEO4J_PASSWORD","password")
)

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
COM = 'Comment'

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

    def __init__(self, login: tuple[str, str] | None = None, uri=URI, driverAuth=AUTH):
        self.driver = GraphDatabase.driver(uri, auth=driverAuth)
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
                          final=None):
        """Creates if not exist nodes a, b, and the relation (a)->[:rlab]->(b)

        [a/b][lab/dic] = [label/dictionary] of [first/second] object
        r[lab/dic] = [label/dictionary] of relation
        final = the last operation"""
        A = alab
        B = blab
        R = rlab
        if final == None: 
            final = f'RETURN {A},{R},{B}'
        else:
            op, final = final.split(' ')
            final = final.split(',')
            for i,w in enumerate(final):
                for o,n in {'a':A,'b':B,'r':rlab}.items():
                    w = w[0].replace(o,n) + w[1:]
                final[i] = w
            final = op + ' ' + ','.join(final)

        query, values = "", {}
        a = ({'name':A,'labels':alab,'d':adic},createA)
        b = ({'name':B,'labels':blab,'d':bdic},createB)

        for var in (a,b):
            s,v = _labelQuery(**var[0], op=(MERGE if var[1] else MATCH))
            query = '\n'.join([query, s, (_giveId(var[0]['name']) if var[1] else ''),])
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
        r = self._abRel(DOC, doc, HOS, hos, WORKS_AT, rdic={})
        for rev in reviews:
            rev['date'] = str(datetime.now())
            r += self._abRel(USR,
                                  {'username': ''.join([chr(randint(65,90)) for _ in range(32)])},
                                  REV, rev, WROTE, rdic={})
            r += self._abRel(REV, rev, DOC, doc, REVIEWS, rdic={})
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
    
    def createUser(self, login:dict, role: str = "patient") -> bool:
        valid_roles = {'patient', 'doctor', 'admin'}
        if role not in valid_roles:
            return False

        try:
            #Create user in the DMBS
            self.driver.execute_query("""\
                    CREATE USER $username
                    SET PASSWORD $password CHANGE NOT REQUIRED""",
                **login)
        except Exception as error:
            print("createUser error:", error)
            return False

        #Create user as a database object
        self.driver.execute_query(
            "MERGE (u:User {username: $username}) SET u.role = $role, u.is_app_user = true",
            username=login["username"], role=role
        )
        return True

    def getUserRole(self, username: str) -> str | None:
        results = self._executeQuery(
            """
            MATCH (u:User {username: $username})
            RETURN u.role
            """,
            username=username
        )

        if not results:
            return None

        role = results[0][0]

        if role is None:
            return "patient"

        return role


    def deleteUser(self, username):
        self._executeQuery("""DROP USER $user IF EXISTS""", user=username)
        self._executeQuery("""MATCH (u:User {username: $user})\
                    DETACH DELETE u""", user=username)

    def createDoctor(self, doctor:dict, hospital:dict):
        self._abRel(DOC, doctor, HOS, hospital, WORKS_AT)

    def createReview(self, review: dict, doctor: dict):
        """Allow one review per user for each doctor."""
        existing_reviews = self._executeQuery(
            f"""
            MATCH
                (u:{USR} {{username: $username}})
                -[:{WROTE}]->
                (r:{REV})
                -[:{REVIEWS}]->
                (d:{DOC} {{uuid: $doctor_uuid}})
            RETURN r.uuid
            """,
            username=self.uname["username"],
            doctor_uuid=doctor["uuid"]
        )

        for result in existing_reviews:
            self.deleteUserReview(self.uname["username"], result[0])

        self._abRel(USR,self.uname,REV,giveDate(review), WROTE, rdic={}, createA=False)
        self._abRel(REV,review,DOC,doctor,REVIEWS, rdic={}, createA=False, createB=False)

    def deleteReview(self, review, user:dict|None=None):
        """Do not specify user if used to delete own review"""
        if user == None:
            user = self.uname
        self._abRel(USR, user, REV, review, WROTE, rdic={},
                    createA=False, createB=False, final='DETACH DELETE b')

    def getUserReviews(self, username: str) -> list[dict]:
        results = self._executeQuery(
            f"""
            MATCH (u:{USR} {{username: $username}})-[:{WROTE}]->(r:{REV})-[:{REVIEWS}]->(d:{DOC})
            RETURN r, d
            ORDER BY r.date DESC
            """, username = username)

        return [{
                "review": row[0],
                "doctor": row[1]
            }
            for row in results
        ]

    def deleteUserReview(self,username: str, review_uuid: str
    ) -> bool:
        results = self._executeQuery(
            f"""
            MATCH (u:{USR} {{username: $username}})-[:{WROTE}]->(r:{REV} {{uuid: $review_uuid}})
            WITH r DETACH DELETE r RETURN true
            """,
            username=username,
            review_uuid=review_uuid
        )

        return len(results) > 0

    def createComment(self, comment:str, target_uuid:str):
        c = self._abRel(USR, self.uname, COM, giveDate({'body':comment}), 
                        WROTE, final='RETURN b', rdic={})[0][0]
        c,v = _dictQuery(d=c)
        self._executeQuery(f"""MATCH (target:{COM}|{REV} {{uuid:'{target_uuid}'}})
                           MATCH (comment:{COM} {c}) WITH comment, target
                           MERGE (comment)-[:{RESPONDS_TO}]->(target)""",**v)

    def getComments(self, target_uuid:str):
        comments = [{'comment':i,'user':j, 'replies':[]} for i,j in self._executeQuery(
            f"""MATCH (target:{REV}|{COM} {{uuid:'{target_uuid}'}}
                       )<-[:Responds_To]-(comment) 
            WITH comment
            MATCH (u:User)-[:Wrote]->(comment)
            RETURN comment, u
            """)]
        if len(comments) != 0:
            for c in comments:
                c['replies'] = self.getComments(c['comment']['uuid'])
        return comments

    def canDoctorRespondToReview(self, username: str, review_uuid: str) -> bool:
        results = self._executeQuery(
            f"""
            MATCH (u:{USR} {{username: $username}})
                  -[:{IS}]->(d:{DOC})
                  <-[:{REVIEWS}]-(r:{REV} {{uuid: $review_uuid}})
            RETURN r
            """,
            username=username,
            review_uuid=review_uuid
        )

        return len(results) > 0

    def createReport(self, review:dict, reason:str):
        self._abRel(USR, self.uname, REV, {'uuid':review['uuid']}, REPORTED, rdic={},
                    createA=False, createB=False, final='DELETE r')
        report = {BODY:reason, DATE:str(datetime.now())}
        return self._abRel(USR, self.uname, REV, review, REPORTED, rdic=report, createB=False, createA=False)

    def getReports(self):
        result = self._executeQuery(f"""MATCH (u:{USR})-[r:{REPORTED}]->(c)
                                    RETURN u,r,r.body,c """)
        return [{'reporter':r[0],'reason':r[2],'reportedContent':r[3]} for r in result]

    def dismissReport(self, username: str, review_uuid: str):
        self._abRel(USR,{"username": username},REV,{"uuid": review_uuid},REPORTED,createA=False,createB=False,final="DELETE r")
        return True

    def deleteReviewByUuid(self, review_uuid: str) -> bool:
        results = self._executeQuery(
            f"MATCH (r:{REV} {{uuid: $review_uuid}}) WITH r DETACH DELETE r RETURN true",
            review_uuid=review_uuid
        )
        return len(results) > 0

    def requestVerification(self, doctor, reason):
        self._abRel(USR, self.uname, DOC, doctor, MIGHT_BE, rdic={BODY:reason}, createA=False, createB=False)

    def getVerificationRequests(self):
        res = self._abRel(USR,{},DOC,{},MIGHT_BE, createA=False, createB=False,
                          final=f'RETURN a,r,r.{BODY},b')
        return [{'user':r[0],'reason':r[2],'doctor':r[3]} for r in res]

    def approveVerification(self, user: dict, doctor: dict):
        # self._abRel(USR,user,DOC,doctor,MIGHT_BE, rdic={}, createA=False, createB=False,
        #             final=f'DELETE r')
        self._executeQuery(f"""
            MATCH (u:{USR})-[r:{MIGHT_BE}]->(d:{DOC})
            WHERE d.uuid = $doctor_uuid
            DELETE r
        """, doctor_uuid=doctor["uuid"]
        )
        self._abRel(USR,user,DOC,doctor,IS, rdic={}, createA=False, createB=False)
        #Promote the application accoutn to doctor
        return self.updateUserRole(user["username"], "doctor")
    
    def denyVerification(self, user, doctor):
        self._abRel(USR,user,DOC,doctor,MIGHT_BE, rdic={}, createA=False, createB=False,
                    final=f'DELETE r')
        return True
    
    def isDoctorVerified(self, doctor):
        result = self._executeQuery(f"""
            MATCH (u:{USR})-[:{IS}]->(d:{DOC})
            WHERE d.uuid = $doctor_uuid
            RETURN u
        """, doctor_uuid=doctor["uuid"])

        return len(result) > 0
    
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

    def search(self, search:str, limit:int=50, offset:int=0, label:str='', props:dict|None=None):
        """Fuzzyfind, most relevant node at index 0"""

        search = ' '.join([c+'~' for c in search.split(' ')]) # lucine fuzzyfind syntax
        
        query = [f"CALL db.index.fulltext.queryNodes('names','{search}') Yield node"]
        filter = None
        if label != '' or props != None:
            filter = []
            if label != '':
                filter.append(f'node IS {label}')
            if props != None:
                for k,v in props.items():
                    filter.append(f"node.{k} = '{v}'")
            filter[0] = 'WHERE ' + filter[0]
            filter = ' AND '.join(filter)
        if filter != None:
            query.append(filter)
        query.append(f'RETURN node OFFSET {offset} LIMIT {limit}')

        return self._executeQuery('\n'.join(query))

    def findNear(self, zip:str, range:int)->list:
        """Returns a list of hospitals within range of a zip code"""
        validZips = [z for z, coords, in zipcodes.items()
                 if (haversine(zipcodes[zip], coords, unit=Unit.MILES) <= range)]
        return [h[0] for h in self._executeQuery(f"MATCH (h:Hospital) WHERE h.zip IN {validZips} RETURN h")]

    def getDIdsFromHos(self, hospital:dict)->list[str]:
        h,v = _dictQuery(d=hospital)
        return [d[0] for d in self._executeQuery(f'MATCH (d:{DOC})-->(:{HOS} {h})\
                                                        RETURN d.uuid',**v)]

    def findDocNear(self, zip:str, range:int)->list:
        hids = [self.getDIdsFromHos(h) for h in self.findNear(zip, range)]
        return [self.getDoctorProfile(h) for h in hids]

    def _tests(self):
        testdoc = {NAME:'Dr. Kimberly Ireland'}
        print('doc rating', s.getDoctorRating(testdoc) == 4.905000000000001)

        s.requestVerification(testdoc, 'im witawawy hiwm')
        print('verification', s.getVerificationRequests()[0]['reason'] == 'im witawawy hiwm')
        s.approveVerification(self.uname, testdoc)
        print('search',
              s.search('kimb irelnd Ophthalmologist', label=DOC)[0][0]['name']
              == testdoc['name'])
        #rev = s.getDoctorProfile(s.searchDoctors('kimb irelnd Ophthalmologist')[0]['doctor']['uuid'])['reviews'][0]['uuid']
        #s.createComment('aaahhhhhhhhhhaaaaAAAAAAAA',rev)
        #print(s.getComments(rev))

        #[print(s.getDoctorProfile(i)['doctor']) for i in s.getDIdsFromHos(s.findNear('32304',300)[0])]
        #print(s.getAllDoctors(5))
        #print(s.getSpecialties())
        #[print(i) for i in s.searchDoctors('plastic', 5)]
        s.getDoctorProfile(s.search('ireland')[0][0]['uuid'])

    #====================#
    # Requested Functions#
    #====================#

    def searchDoctors( self, search_term: str, limit: int = 50, offset: int = 0) -> list[dict]:
        ls = []
        for e in self.search(search_term, limit, offset):
            if 'specialty' in e[0]:
                ls.append(e[0])
            else:
                d,v = _dictQuery(d=e[0])
                ls += [i[0] for i in self._executeQuery(
                    f"""MATCH (d:{DOC})-[:{WORKS_AT}]->(:{HOS} {d}) RETURN d""",**v)]
        resList = []
        for d in ls:
            profile = self.getDoctorProfile(d['uuid'])

            if profile is None:
                continue
            res = {}
            for k,v in profile.items():
                if k != 'reviews':
                    res[k] = v
                else:
                    res['review_count'] = len(v)
            resList.append(res)
        return resList

    def getAllUsers(self) -> list[dict]:
        results = self._executeQuery(
            f"""
            MATCH (u:{USR}) WHERE u.is_app_user = true
            OPTIONAL MATCH (u)-[:{WROTE}]->(r:{REV})
            RETURN u.username, coalesce(u.role, "patient"), count(r)
            ORDER BY toLower(u.username)
            """
        )
        return [
            {
                "username": row[0],
                "role": row[1],
                "review_count": row[2]
            } for row in results
        ]

    def updateUserRole(
            self,
            username: str,
            role: str
    ) -> bool:
        valid_roles = {
            "patient",
            "doctor",
            "admin"
        }

        if role not in valid_roles:
            return False

        results = self._executeQuery(
            f"""
            MATCH (u:{USR} {{username: $username}})
            SET u.role = $role
            RETURN u.role
            """,
            username=username,
            role=role
        )

        return len(results) > 0

    def getLinkedDoctorProfile(
            self,
            username: str
    ) -> dict | None:
        results = self._executeQuery(
            f"""
            MATCH (u:{USR} {{username: $username}})
                  -[:{IS}]->(d:{DOC})
            RETURN d.uuid
            """,
            username=username
        )

        if len(results) == 0:
            return None

        doctor_uuid = results[0][0]

        return self.getDoctorProfile(doctor_uuid)


    def getDoctorProfile( self, doctor_uuid: str) -> dict | None:
        """
        Return:
            {
            "doctor": {...},
            "hospital": {...} or None,
            "average_rating": 4.5,
            "reviews": [...]
            }
        Return None when the doctor does not exist.
        """
        try:
            results = self._executeQuery(
                f"""
                MATCH (d:{DOC} {{uuid: $doctor_uuid}})
                OPTIONAL MATCH (d)-->(h:{HOS})
                Optional Match (d)<-[i:Is]-(u)
                RETURN d, h, i, u
                """,
                doctor_uuid=doctor_uuid
            )
            if not results:
                return None
            try:
                doc, hosp, _, user = results[0]
            except:
                doc, hosp = results[0]
                user = ''
            reviews = self.getDoctorReviews(doc)
            rating  = self.getDoctorRating(doc)
            return {'doctor':doc,'hospital':hosp,'average_rating':rating,'reviews':reviews, 'username':user}
        except Exception as error:
            print("getDoctorProfile error:", error)
            return None

    def getAllDoctors( self,
        limit: int = 20,
        offset: int = 0,
        specialty: str | None = None,
        sort_by: str = "rating"
        ) -> list[dict]:
        """
        Return doctors for a browse-all page with pagination,
        filtering, ratings, review counts, and hospital information.
        """
        query = "MATCH (doctor:Doctor)<-[:Reviews]-(reviews)"
        if specialty != None:
            query += f"WHERE doctor.specialty = '{specialty}'"
        query += f"""RETURN doctor, avg(toInteger(reviews.rating)) as average_rating
                 ORDER BY average_rating DESC OFFSET {offset*limit} LIMIT {limit}"""
        docs =  [i for i,_ in self._executeQuery(query)]
                      
        return [{k:v for k,v in self.getDoctorProfile(d['uuid']).items()
                 if k != 'reviews'} for d in docs]

    def getSpecialties(self) -> list[str]:
        """
        Return every distinct doctor specialty in alphabetical order.
        """ 
        return [i[0] for i in self._executeQuery(f"""MATCH (d:Doctor) WITH d.specialty
                                                 as specialty
                           RETURN DISTINCT specialty ORDER BY specialty""")]


if __name__ == '__main__':
    s = Session(AUTH)
    s._tests()

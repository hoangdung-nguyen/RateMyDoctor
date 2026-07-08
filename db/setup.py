#!/usr/bin/env python3
from neo4j import GraphDatabase
from database import URI, DB

ADMIN = 'neo4j'

if __name__ == '__main__':
    auth = (ADMIN, input(f'{ADMIN} pass: '))
    with GraphDatabase.driver(URI, auth=auth) as driver:
        driver.execute_query("""CREATE DATABASE $db""", db=DB)

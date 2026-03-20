#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
from app.core.database import db

db.connect()
col = db.db["trump_statements"]
total = col.count_documents({})
enriched = col.count_documents({"llm_enriched": True})
null_field = col.count_documents({"llm_enriched": None})
false_field = col.count_documents({"llm_enriched": False})
print(f"Total: {total}")
print(f"llm_enriched=True:  {enriched}")
print(f"llm_enriched=None:  {null_field}")
print(f"llm_enriched=False: {false_field}")
db.disconnect()

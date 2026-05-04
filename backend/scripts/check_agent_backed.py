#!/usr/bin/env python3
import sys
import os
import requests

def main():
    api_base = os.environ.get("API_BASE_URL", "http://localhost:8000")
    job_id = os.environ.get("SCAN_JOB_ID", "")
    
    if not job_id:
        print("Missing SCAN_JOB_ID in environment.")
        sys.exit(1)
        
    url = f"{api_base}/admin/audits/agent-backed?job_id={job_id}"
    resp = requests.get(url)
    
    if not resp.ok:
        print(f"FAIL: admin endpoint returned {resp.status_code}: {resp.text}")
        sys.exit(1)
        
    data = resp.json()
    total = data.get("total_benefits", 0)
    pct = data.get("agent_backed_pct", 0.0)
    
    print(f"Agent-backed stats for {job_id}: total={total}, pct={pct}%")
    
    if total < 5:
        print(f"FAIL: Expected >= 5 benefits for Luis scan, got {total}")
        sys.exit(1)
        
    if pct < 100.0:
        print(f"FAIL: Agent-backed percentage is {pct}%, expected 100.0%")
        sys.exit(1)
        
    print("SUCCESS: 100% of verifications were agent-backed.")

if __name__ == "__main__":
    main()
